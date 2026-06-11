import { useState, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { FastForward, FileText, ListVideo, MessageCircle, PlayCircle, X } from 'lucide-react'
import FriendView from './FriendView'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import './App.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

const LATEX_COMMAND_PATTERN = String.raw`\\(?:frac|sqrt|left|right|cdot|times|div|sum|int|text|log|ln|sin|cos|tan|theta|pi|alpha|beta|gamma|Delta|le|ge|neq|approx|infty|lim)`

const normalizeMathMarkdown = (markdown: string) => {
  const protectedLatexParens = markdown
    .replace(/\\left\(/g, String.raw`\left\lparen`)
    .replace(/\\right\)/g, String.raw`\right\rparen`)
    .replace(/\\left\[/g, String.raw`\left\lbrack`)
    .replace(/\\right\]/g, String.raw`\right\rbrack`)

  return protectedLatexParens
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_, expr: string) => `\n\n$$\n${expr.trim()}\n$$\n\n`)
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_, expr: string) => `$${expr.trim()}$`)
    .replace(
      new RegExp(String.raw`\((\s*(?=[^\n]*${LATEX_COMMAND_PATTERN}|[^\n]*[A-Za-z]\s*[_^])[^\n]*?)\)(?=[,.;:]?\s|$)`, 'g'),
      (match: string, expr: string) => {
        const trimmed = expr.trim()
        return trimmed && !trimmed.includes('$') ? `$${trimmed}$` : match
      },
    )
    .replace(/\(\s*([abmnrtxy])\s*\)/g, '$$$1$$')
}

const EXAMPLE_IMAGE_PATHS = [
  '/assets/Examples/example_1.png',
  '/assets/Examples/example_3.png',
  '/assets/Examples/example_6.png',
  '/assets/Examples/example_7.png',
]

const LECTURES = [
  {
    id: 'chapter-4-1',
    title: 'Ch. 4.1 Exponential Functions',
    description: 'Learn the definition and core behavior of exponential functions.',
    src: '/assets/video.mp4',
    duration: '20:36',
  },
]

interface Message {
  role: 'user' | 'assistant'
  text: string
  id?: number
  attachments?: ChatAttachment[]
}

interface ChatAttachment {
  type: 'passage' | 'figure'
  text: string
  imageUrl?: string
}

interface PastedImageSelection {
  image: string
  name: string
}

interface Figure {
  id: string
  page: number
  bbox: { x: number; y: number; x2: number; y2: number }
  label: string
  description: string
}

interface SelectionButtonAnchor {
  left: number
  top: number
}

type LessonState = 'idle' | 'playing' | 'paused' | 'question'
type AppMode = 'lesson' | 'friend' | 'playlist'

function App() {
  const [lessonInput, setLessonInput] = useState('')
  const [lessonMessages, setLessonMessages] = useState<Message[]>([])
  const [pendingPdfSelection, setPendingPdfSelection] = useState('')
  const [selectionButtonAnchor, setSelectionButtonAnchor] = useState<SelectionButtonAnchor | null>(null)
  const [pdfSelections, setPdfSelections] = useState<string[]>([])

  const [numPages, setNumPages] = useState(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [figures, setFigures] = useState<Figure[]>([])
  const [pendingFigureSelection, setPendingFigureSelection] = useState<{ figure: Figure; image: string | null } | null>(null)
  const [figureSelections, setFigureSelections] = useState<{ figure: Figure; image: string | null }[]>([])
  const [pastedImageSelections, setPastedImageSelections] = useState<PastedImageSelection[]>([])

  const [lessonState, setLessonState] = useState<LessonState>('idle')
  const [showChat, setShowChat] = useState(false)
  const [showPdf, setShowPdf] = useState(false)
  const [hasOpenedPdf, setHasOpenedPdf] = useState(false)
  const [appMode, setAppMode] = useState<AppMode>('friend')
  const [selectedLectureId, setSelectedLectureId] = useState(LECTURES[0].id)
  const [lectureThumbnails, setLectureThumbnails] = useState<Record<string, string>>({})

  // Autorater (Isabella) mode state
  const [autoraterMode, setAutoraterMode] = useState(false)
  const [autoraterStarted, setAutoraterStarted] = useState(false)
  const [autoraterLoading, setAutoraterLoading] = useState(false)
  const [exampleInput, setExampleInput] = useState('')
  const [exampleMessages, setExampleMessages] = useState<Message[]>([])
  const [currentExampleIndex, setCurrentExampleIndex] = useState(0)
  const [currentExampleImage, setCurrentExampleImage] = useState(EXAMPLE_IMAGE_PATHS[0])

  const scrollRef = useRef<HTMLDivElement>(null)
  const pdfPanelRef = useRef<HTMLDivElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const pdfScrollTopRef = useRef(0)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const messageIdRef = useRef(0)
  const activeInput = autoraterMode ? exampleInput : lessonInput
  const activeMessages = autoraterMode ? exampleMessages : lessonMessages

  const clearPendingPdfSelection = () => {
    setPendingPdfSelection('')
    setSelectionButtonAnchor(null)
  }

  const clearChatContext = () => {
    setPdfSelections([])
    clearPendingPdfSelection()
    setPendingFigureSelection(null)
    setFigureSelections([])
    setPastedImageSelections([])
    window.getSelection()?.removeAllRanges()
  }

  const resetLessonPage = () => {
    setLessonInput('')
    setLessonMessages([])
    clearChatContext()
    setShowChat(false)
    setShowPdf(false)
    setHasOpenedPdf(false)
    pdfScrollTopRef.current = 0
  }

  const resetExamplePage = () => {
    setExampleInput('')
    setExampleMessages([])
    clearChatContext()
  }

  const getSelectionButtonAnchor = (selectionRect: DOMRect): SelectionButtonAnchor | null => {
    const panelRect = pdfPanelRef.current?.getBoundingClientRect()
    if (!panelRect) return null

    const buttonHalfWidth = 66
    const topPadding = 88
    const x = selectionRect.left + selectionRect.width / 2 - panelRect.left
    const y = selectionRect.top - panelRect.top - 8

    return {
      left: Math.min(Math.max(x, buttonHalfWidth), panelRect.width - buttonHalfWidth),
      top: Math.max(y, topPadding),
    }
  }

  const getAttachmentPreview = (text: string, maxLength = 180) => {
    const normalized = text.replace(/\s+/g, ' ').trim()
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
  }

  const readImageFileAsDataUrl = (file: File) => new Promise<PastedImageSelection>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({
      image: String(reader.result),
      name: file.name || 'Pasted image',
    })
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })

  const loadImageAsDataUrl = async (src: string) => {
    const response = await fetch(src)
    if (!response.ok) throw new Error(`Failed to load ${src}`)
    const blob = await response.blob()
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(blob)
    })
  }

  const captureVideoThumbnail = (src: string) => new Promise<string>((resolve, reject) => {
    const video = document.createElement('video')
    video.src = src
    video.muted = true
    video.preload = 'metadata'
    video.playsInline = true

    const cleanup = () => {
      video.removeAttribute('src')
      video.load()
    }

    video.onloadedmetadata = () => {
      video.currentTime = Math.min(3, Math.max(0, (video.duration || 6) * 0.12))
    }
    video.onseeked = () => {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 640
      canvas.height = video.videoHeight || 360
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        cleanup()
        reject(new Error('Could not capture video thumbnail'))
        return
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const dataUrl = canvas.toDataURL('image/jpeg', 0.82)
      cleanup()
      resolve(dataUrl)
    }
    video.onerror = () => {
      cleanup()
      reject(new Error(`Could not load ${src}`))
    }
  })

  const getSelectionAttachments = (): ChatAttachment[] => [
    ...pdfSelections.map(selection => ({
      type: 'passage' as const,
      text: getAttachmentPreview(selection),
    })),
    ...figureSelections.map(selection => ({
      type: 'figure' as const,
      text: selection.figure.description || selection.figure.label,
      imageUrl: selection.image || undefined,
    })),
    ...pastedImageSelections.map(selection => ({
      type: 'figure' as const,
      text: selection.name,
      imageUrl: selection.image,
    })),
  ]

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [activeMessages, showChat])

  useEffect(() => {
    if (!showPdf || !pdfContainerRef.current) return
    const observer = new ResizeObserver(entries => {
      setContainerWidth(Math.max(320, Math.floor(entries[0].contentRect.width)))
    })
    observer.observe(pdfContainerRef.current)
    return () => observer.disconnect()
  }, [showPdf, autoraterMode])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (pdfScrollRef.current) {
        pdfScrollRef.current.scrollTop = pdfScrollTopRef.current
      }
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [showPdf, autoraterMode])

  useEffect(() => {
    if (!showChat) return
    const timeout = window.setTimeout(() => chatInputRef.current?.focus(), 100)
    return () => window.clearTimeout(timeout)
  }, [showChat])

  useEffect(() => {
    if (!pendingPdfSelection) return

    const handleSelectionChange = () => {
      const selection = window.getSelection()
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        setPendingPdfSelection('')
        setSelectionButtonAnchor(null)
      }
    }

    document.addEventListener('selectionchange', handleSelectionChange)
    return () => document.removeEventListener('selectionchange', handleSelectionChange)
  }, [pendingPdfSelection])

  useEffect(() => {
    fetch('/assets/figures.json')
      .then(r => r.json())
      .then(setFigures)
      .catch(console.error)
  }, [])

  useEffect(() => {
    let cancelled = false
    LECTURES.forEach(lecture => {
      captureVideoThumbnail(lecture.src)
        .then(thumbnail => {
          if (!cancelled) {
            setLectureThumbnails(prev => ({ ...prev, [lecture.id]: thumbnail }))
          }
        })
        .catch(console.error)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const handleVideoShortcuts = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, [contenteditable="true"]')) return
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return

      const video = videoRef.current
      if (!video) return

      e.preventDefault()
      const delta = e.key === 'ArrowRight' ? 5 : -5
      const duration = Number.isFinite(video.duration) ? video.duration : Number.POSITIVE_INFINITY
      video.currentTime = Math.min(Math.max(video.currentTime + delta, 0), duration)
    }

    window.addEventListener('keydown', handleVideoShortcuts)
    return () => window.removeEventListener('keydown', handleVideoShortcuts)
  }, [])

  const handlePageClick = (e: React.MouseEvent<HTMLDivElement>, pageNumber: number) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const scale = containerWidth / 595.3
    const ptX = (e.clientX - rect.left) / scale
    const ptY = (e.clientY - rect.top) / scale
    const found = figures.find(f =>
      f.page === pageNumber &&
      ptX >= f.bbox.x && ptX <= f.bbox.x2 &&
      ptY >= f.bbox.y && ptY <= f.bbox.y2
    )
    if (!found) {
      setPendingFigureSelection(null)
      if (!pendingPdfSelection.trim()) setSelectionButtonAnchor(null)
      return
    }

    let image: string | null = null
    const sourceCanvas = e.currentTarget.querySelector('canvas') as HTMLCanvasElement | null
    if (sourceCanvas) {
      const renderScale = sourceCanvas.width / containerWidth
      const sx = found.bbox.x * scale * renderScale
      const sy = found.bbox.y * scale * renderScale
      const sw = (found.bbox.x2 - found.bbox.x) * scale * renderScale
      const sh = (found.bbox.y2 - found.bbox.y) * scale * renderScale
      const out = document.createElement('canvas')
      out.width = Math.max(1, Math.round(sw))
      out.height = Math.max(1, Math.round(sh))
      const ctx = out.getContext('2d')
      if (ctx) {
        ctx.drawImage(sourceCanvas, sx, sy, sw, sh, 0, 0, out.width, out.height)
        image = out.toDataURL('image/png')
      }
    }

    setPendingFigureSelection({ figure: found, image })
    setSelectionButtonAnchor(getSelectionButtonAnchor(new DOMRect(
      rect.left + found.bbox.x * scale,
      rect.top + found.bbox.y * scale,
      (found.bbox.x2 - found.bbox.x) * scale,
      (found.bbox.y2 - found.bbox.y) * scale,
    )))
  }

  const handleMouseUp = () => {
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) {
      clearPendingPdfSelection()
      return
    }

    const text = selection.toString().trim()
    if (!text) {
      clearPendingPdfSelection()
      return
    }

    const range = selection.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    setPendingPdfSelection(text)
    setSelectionButtonAnchor(getSelectionButtonAnchor(rect))
  }

  const confirmSelection = () => {
    const text = pendingPdfSelection.trim()
    if (text) {
      setPdfSelections([text])
      window.getSelection()?.removeAllRanges()
    }
    if (pendingFigureSelection) {
      setFigureSelections([pendingFigureSelection])
    }
    clearPendingPdfSelection()
    setPendingFigureSelection(null)
    setShowChat(true)
  }

  const removePdfSelectionAt = (idx: number) => {
    setPdfSelections(prev => prev.filter((_, i) => i !== idx))
  }

  const removeFigureSelectionAt = (idx: number) => {
    setFigureSelections(prev => prev.filter((_, i) => i !== idx))
  }

  const removePastedImageSelectionAt = (idx: number) => {
    setPastedImageSelections(prev => prev.filter((_, i) => i !== idx))
  }

  const handleChatPaste = async (e: React.ClipboardEvent<HTMLInputElement>) => {
    const imageFiles = Array.from(e.clipboardData.files).filter(file => file.type.startsWith('image/'))
    if (imageFiles.length === 0) return

    e.preventDefault()
    try {
      const images = await Promise.all(imageFiles.map(readImageFileAsDataUrl))
      setPastedImageSelections(prev => [...prev, ...images])
      setShowChat(true)
    } catch (error) {
      console.error('Failed to read pasted image:', error)
    }
  }

  const startAutoraterSession = async (imageB64: string, loadingText = 'Analyzing example...') => {
    setAutoraterLoading(true)
    const msgId = ++messageIdRef.current
    setExampleMessages(prev => [...prev, { role: 'assistant', text: loadingText, id: msgId }])

    try {
      const response = await fetch('http://localhost:8000/api/v1/autorater/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_b64: imageB64 }),
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => response.statusText)
        throw new Error(`HTTP ${response.status}: ${detail}`)
      }
      const data = await response.json()
      setExampleMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: `Isabella: ${data.opener}` } : m))
      setAutoraterStarted(true)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error starting autorater:', msg)
      setExampleMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, text: `Failed to start: ${msg}` } : m
      ))
    } finally {
      setAutoraterLoading(false)
    }
  }

  const startExampleSession = async (exampleIndex: number, resetConversation: boolean) => {
    const imagePath = EXAMPLE_IMAGE_PATHS[exampleIndex]
    if (!imagePath) return

    setCurrentExampleIndex(exampleIndex)
    setCurrentExampleImage(imagePath)
    setAutoraterMode(true)
    setAutoraterStarted(false)
    setShowChat(true)
    setHasOpenedPdf(true)
    setShowPdf(true)
    clearPendingPdfSelection()
    setPendingFigureSelection(null)
    if (resetConversation) {
      resetExamplePage()
    }

    try {
      const imageB64 = await loadImageAsDataUrl(imagePath)
      await startAutoraterSession(imageB64, `Loading Example ${exampleIndex + 1}...`)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error loading example:', msg)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Failed to load example: ${msg}` }])
      setAutoraterLoading(false)
    }
  }

  const sendAutoraterMessage = async () => {
    const messageText = exampleInput.trim()
    if (!messageText || autoraterLoading) return

    setExampleMessages(prev => [...prev, { role: 'user', text: messageText }])
    setExampleInput('')
    setAutoraterLoading(true)

    try {
      const response = await fetch('http://localhost:8000/api/v1/autorater/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Isabella: ${data.reply}` }])
      if (data.next_opener) {
        setExampleMessages(prev => [...prev, { role: 'assistant', text: `Isabella: ${data.next_opener}` }])
      }
      if (data.is_done) {
        const nextExampleIndex = currentExampleIndex + 1
        if (nextExampleIndex < EXAMPLE_IMAGE_PATHS.length) {
          await startExampleSession(nextExampleIndex, false)
        } else {
          setAutoraterStarted(false)
          setExampleMessages(prev => [...prev, { role: 'assistant', text: 'Isabella: Great work. You finished all of the examples.' }])
          window.setTimeout(() => {
            endExampleSession()
          }, 1200)
        }
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error in autorater chat:', msg)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Error: ${msg}` }])
    } finally {
      setAutoraterLoading(false)
    }
  }

  const sendMessage = async () => {
    if (autoraterStarted && autoraterMode) {
      await sendAutoraterMessage()
      return
    }
    const hasContext = pdfSelections.length > 0 || figureSelections.length > 0 || pastedImageSelections.length > 0
    const messageText = lessonInput.trim() || (hasContext ? 'Explain this.' : '')
    if (!messageText) return

    const attachments = getSelectionAttachments()
    setShowChat(true)
    setLessonMessages(prev => [...prev, { role: 'user', text: messageText, attachments }])
    setLessonInput('')

    const body: { message: string; pdf_context?: string; figure_context?: string; figure_images?: string[]; current_video_time?: number } = { message: messageText }
    if (pdfSelections.length > 0) {
      body.pdf_context = pdfSelections
        .map((s, i) => `Passage ${i + 1}:\n"""\n${s}\n"""`)
        .join('\n\n')
    }
    const figureImages = [
      ...figureSelections
        .map(s => s.image)
        .filter((img): img is string => !!img),
      ...pastedImageSelections.map(s => s.image),
    ]
    if (figureSelections.length > 0) {
      body.figure_context = figureSelections
        .map((s, i) => {
          const desc = s.figure.description ? s.figure.description : '(no description)'
          return `Figure ${i + 1} — Label: ${s.figure.label}. Description: ${desc}`
        })
        .join('\n\n')
    }
    if (figureImages.length > 0) body.figure_images = figureImages
    if (videoRef.current && videoRef.current.currentTime > 0) {
      body.current_video_time = videoRef.current.currentTime
    }

    setPdfSelections([])
    clearPendingPdfSelection()
    setFigureSelections([])
    setPendingFigureSelection(null)
    setPastedImageSelections([])
    window.getSelection()?.removeAllRanges()

    const msgId = ++messageIdRef.current
    setLessonMessages(prev => [...prev, { role: 'assistant', text: '', id: msgId }])

    try {
      const response = await fetch('http://localhost:8000/api/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`)
      }
      await consumeSSE(response.body, msgId)
    } catch (error) {
      console.error('Error:', error)
      setLessonMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: '⚠️ Failed to reach the assistant.' } : m))
    }
  }

  const consumeSSE = async (stream: ReadableStream<Uint8Array>, msgId: number) => {
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let sepIdx
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx)
          buffer = buffer.slice(sepIdx + 2)

          for (const line of rawEvent.split('\n')) {
            if (!line.startsWith('data: ')) continue
            const data = line.slice(6)
            try {
              const obj = JSON.parse(data)
              if (typeof obj.delta === 'string') {
                setLessonMessages(prev => prev.map(m =>
                  m.id === msgId ? { ...m, text: m.text + obj.delta } : m
                ))
              } else if (obj.error) {
                setLessonMessages(prev => prev.map(m =>
                  m.id === msgId ? { ...m, text: `⚠️ ${obj.error}` } : m
                ))
              }
            } catch {
              // Ignore non-JSON chunks (e.g. heartbeats).
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  const toggleTextbook = () => {
    setHasOpenedPdf(true)
    setShowPdf(prev => !prev)
  }

  const enterAutoraterMode = () => {
    if (videoRef.current) {
      videoRef.current.pause()
    }
    setLessonState('paused')
    void startExampleSession(0, true)
  }

  const endExampleSession = () => {
    setAutoraterMode(false)
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    resetExamplePage()
    setCurrentExampleIndex(0)
    setCurrentExampleImage(EXAMPLE_IMAGE_PATHS[0])
    setShowChat(false)
    setShowPdf(false)
    setAppMode('friend')
  }

  const toggleChat = () => {
    setShowChat(prev => !prev)

    const selection = window.getSelection()
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      clearPendingPdfSelection()
    }
  }

  const selectedLecture = LECTURES.find(lecture => lecture.id === selectedLectureId) ?? LECTURES[0]

  const openPlaylist = () => {
    videoRef.current?.pause()
    setLessonState('paused')
    setShowPdf(false)
    setShowChat(false)
    setAppMode('playlist')
  }

  const openLecture = (lectureId: string) => {
    setSelectedLectureId(lectureId)
    setAutoraterMode(false)
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    resetLessonPage()
    setAppMode('lesson')
    setLessonState('idle')
  }

  if (appMode === 'friend') {
    return (
      <div className="main-layout">
        <FriendView onExit={openPlaylist} />
      </div>
    )
  }

  if (appMode === 'playlist') {
    const firstLectureThumbnail = lectureThumbnails[LECTURES[0].id]
    return (
      <div className="main-layout playlist-view">
        <aside className="playlist-hero">
          <div className="playlist-card">
            {firstLectureThumbnail ? (
              <img src={firstLectureThumbnail} alt="" className="playlist-cover" />
            ) : (
              <div className="playlist-cover playlist-cover-placeholder" />
            )}
            <div className="playlist-card-body">
              <p className="playlist-kicker">Lecture Playlist</p>
              <h1>Exponential and Logarithmic Functions</h1>
              <button className="playlist-play-all" onClick={() => openLecture(LECTURES[0].id)}>
                <PlayCircle size={18} fill="currentColor" />
                Play first lecture
              </button>
            </div>
          </div>
        </aside>

        <main className="playlist-main">
          <div className="lecture-list" aria-label="Lecture videos">
            {LECTURES.map((lecture, index) => (
              <button
                key={lecture.id}
                className={`lecture-row ${lecture.id === selectedLectureId ? 'active' : ''}`}
                onClick={() => openLecture(lecture.id)}
              >
                <span className="lecture-index">{index + 1}</span>
                <span className="lecture-thumb-wrap">
                  {lectureThumbnails[lecture.id] ? (
                    <img src={lectureThumbnails[lecture.id]} alt="" className="lecture-thumb" />
                  ) : (
                    <span className="lecture-thumb lecture-thumb-placeholder" />
                  )}
                  <span className="lecture-duration">{lecture.duration}</span>
                </span>
                <span className="lecture-meta">
                  <strong>{lecture.title}</strong>
                  <span>AI HomeSchooling · {lecture.description}</span>
                </span>
              </button>
            ))}
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className={`main-layout${autoraterMode ? ' autorater-screen' : ''}`}>
      {!autoraterMode && (
      <div className="teacher-view">
        <video
          ref={videoRef}
          src={selectedLecture.src}
          className="character-video"
          controls
          preload="metadata"
          onPlay={() => setLessonState('playing')}
          onPause={() => setLessonState('paused')}
          onEnded={() => setLessonState('paused')}
          playsInline
        />

        {lessonState === 'question' && (
          <div className="lesson-progress">Asking question</div>
        )}

        <button className="playlist-return" onClick={openPlaylist}>
          <ListVideo size={17} />
          Lecture playlist
        </button>

        <div className="lesson-buttons" aria-label="Lesson controls">
          <button
            className={`btn-question ${autoraterMode ? 'active' : ''}`}
            onClick={enterAutoraterMode}
            aria-label="Practice with Isabella"
            title="Practice with Isabella"
          >
            <FastForward size={20} strokeWidth={2.5} />
          </button>
        </div>
      </div>
      )}

      {hasOpenedPdf && (
        <div
          ref={pdfPanelRef}
          className={autoraterMode
            ? 'split-panel autorater-pdf-panel'
            : `floating-panel pdf-panel${showPdf ? '' : ' pdf-panel-hidden'}`}
          aria-hidden={!autoraterMode && !showPdf}
        >
          <div className="panel-header">
            <span>Textbook</span>
            {!autoraterMode && (
            <button className="panel-close" onClick={() => setShowPdf(false)} aria-label="Close textbook">
              <X size={18} />
            </button>
            )}
          </div>

          {!autoraterMode && (pendingPdfSelection || pendingFigureSelection) && (
            <button
              className="btn-pdf-select"
              onClick={confirmSelection}
              onMouseDown={e => e.preventDefault()}
              style={selectionButtonAnchor ? {
                left: selectionButtonAnchor.left,
                right: 'auto',
                top: selectionButtonAnchor.top,
                transform: 'translate(-50%, -100%)',
              } : undefined}
              title="Add this selection to the chat prompt"
            >
              Add to Chat
            </button>
          )}

          <div className="pdf-section" ref={pdfContainerRef} onMouseUp={handleMouseUp}>
            <div
              className="pdf-scroll"
              ref={pdfScrollRef}
              onScroll={e => {
                pdfScrollTopRef.current = e.currentTarget.scrollTop
              }}
            >
              <Document
                file="/assets/Chapter4.pdf"
                onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              >
                {Array.from({ length: numPages }, (_, i) => {
                  const pageNum = i + 1
                  const scale = containerWidth / 595.3
                  return (
                    <div
                      key={pageNum}
                      style={{
                        position: 'relative',
                        cursor: 'default',
                        userSelect: 'auto',
                      }}
                      onClick={e => handlePageClick(e, pageNum)}
                    >
                      <Page
                        pageNumber={pageNum}
                        width={containerWidth}
                        renderTextLayer
                        renderAnnotationLayer={false}
                      />

                      {!autoraterMode && pendingFigureSelection && pendingFigureSelection.figure.page === pageNum && (
                        <div
                          className="figure-pending-highlight"
                          style={{
                            position: 'absolute',
                            left: pendingFigureSelection.figure.bbox.x * scale,
                            top: pendingFigureSelection.figure.bbox.y * scale,
                            width: (pendingFigureSelection.figure.bbox.x2 - pendingFigureSelection.figure.bbox.x) * scale,
                            height: (pendingFigureSelection.figure.bbox.y2 - pendingFigureSelection.figure.bbox.y) * scale,
                            pointerEvents: 'none',
                            boxSizing: 'border-box',
                          }}
                        />
                      )}

                    </div>
                  )
                })}
              </Document>
            </div>
          </div>
        </div>
      )}

      {showChat && (
        <div className={autoraterMode ? 'split-panel autorater-chat-panel' : 'floating-panel chat-panel'}>
          <div className="panel-header">
            <span>{autoraterMode ? 'Solving Examples with Isabella' : 'Chat'}</span>
            {autoraterMode ? (
              <button className="panel-action" onClick={endExampleSession}>
                End example session
              </button>
            ) : (
            <button className="panel-close" onClick={() => setShowChat(false)} aria-label="Close chat">
              <X size={18} />
            </button>
            )}
          </div>

          <div className="chat-view">
            {autoraterMode && (
              <div className="autorater-example-preview">
                <img src={currentExampleImage} alt={`Example ${currentExampleIndex + 1}`} />
              </div>
            )}
            <div className="chat-window" ref={scrollRef}>
              {!autoraterMode && (
                <div className="bubble assistant">
                  <div className="markdown-body">
                    Ask me what you don't know!
                  </div>
                </div>
              )}
              {activeMessages.map((msg, idx) => (
                <div key={idx} className={`bubble ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <div className="markdown-body">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {normalizeMathMarkdown(msg.text)}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="user-message-content">
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="message-attachments">
                          {msg.attachments.map((attachment, attachmentIdx) => (
                            <div
                              key={`${attachment.type}-${attachmentIdx}`}
                              className={`message-attachment-card ${attachment.imageUrl ? 'has-image' : ''}`}
                            >
                              {attachment.imageUrl && (
                                <img
                                  className="message-attachment-image"
                                  src={attachment.imageUrl}
                                  alt="Attached textbook crop"
                                />
                              )}
                              <span className="message-attachment-text">{attachment.text}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <span>{msg.text}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {autoraterMode && autoraterLoading && !autoraterStarted && (
              <div className="autorater-chat-hint">
                Isabella is reading the example...
              </div>
            )}

            {!autoraterMode && (pdfSelections.length > 0 || figureSelections.length > 0 || pastedImageSelections.length > 0) && (
              <div className="context-queue">
                <div className="context-queue-header">
                  <span>Added to chat</span>
                </div>
                {pdfSelections.map((sel, i) => (
                  <div key={`p-${i}`} className="context-queue-card" title={sel}>
                    <span className="context-queue-text">
                      {getAttachmentPreview(sel)}
                    </span>
                    <button
                      className="context-queue-remove"
                      onClick={() => removePdfSelectionAt(i)}
                      aria-label="Remove passage"
                    >
                      ×
                    </button>
                  </div>
                ))}
                {figureSelections.map((sel, i) => (
                  <div
                    key={`f-${i}`}
                    className={`context-queue-card ${sel.image ? 'has-image' : ''}`}
                    title={sel.figure.description || sel.figure.label}
                  >
                    {sel.image && (
                      <img
                        className="context-queue-image"
                        src={sel.image}
                        alt="Attached textbook crop"
                      />
                    )}
                    {!sel.image && (
                      <span className="context-queue-text">
                        {sel.figure.description || sel.figure.label}
                      </span>
                    )}
                    <button
                      className="context-queue-remove"
                      onClick={() => removeFigureSelectionAt(i)}
                      aria-label="Remove figure"
                    >
                      ×
                    </button>
                  </div>
                ))}
                {pastedImageSelections.map((sel, i) => (
                  <div
                    key={`img-${i}`}
                    className="context-queue-card has-image"
                    title={sel.name}
                  >
                    <img
                      className="context-queue-image"
                      src={sel.image}
                      alt="Pasted chat attachment"
                    />
                    <button
                      className="context-queue-remove"
                      onClick={() => removePastedImageSelectionAt(i)}
                      aria-label="Remove pasted image"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="input-area">
              <input
                ref={chatInputRef}
                value={activeInput}
                onChange={e => {
                  if (autoraterMode) {
                    setExampleInput(e.target.value)
                  } else {
                    setLessonInput(e.target.value)
                  }
                }}
                onPaste={handleChatPaste}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder={
                  autoraterMode && !autoraterStarted
                    ? 'Isabella is getting ready…'
                    : autoraterMode
                    ? 'Reply to Isabella…'
                    : 'Type a message…'
                }
                disabled={autoraterLoading || (autoraterMode && !autoraterStarted)}
              />
              <button
                onClick={sendMessage}
                disabled={autoraterLoading || (autoraterMode && !autoraterStarted)}
              >
                {autoraterLoading ? '…' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}

      {!autoraterMode && (
      <div className="quick-actions" aria-label="Study tools">
        <button
          className={`quick-action ${showPdf ? 'active' : ''}`}
          onClick={toggleTextbook}
          aria-label={showPdf ? 'Hide textbook' : 'Show textbook'}
          title={showPdf ? 'Hide textbook' : 'Show textbook'}
        >
          <FileText size={22} />
        </button>
        <button
          className={`quick-action ${showChat ? 'active' : ''}`}
          onClick={toggleChat}
          aria-label={showChat ? 'Hide chat' : 'Show chat'}
          title={showChat ? 'Hide chat' : 'Show chat'}
        >
          <MessageCircle size={22} />
        </button>
      </div>
      )}
    </div>
  )
}

export default App
