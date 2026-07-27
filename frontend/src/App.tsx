import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import FriendView from './FriendView'
import LessonStage from './components/LessonStage'
import PdfPanel from './components/PdfPanel'
import PlaylistView from './components/PlaylistView'
import QuickActions from './components/QuickActions'
import StudyChatPanel from './components/StudyChatPanel'
import { AUTORATER_API_URL, BACKEND_BASE_URL, LECTURES } from './constants'
import type {
  AppMode,
  ChatAttachment,
  Figure,
  FigureSelection,
  LessonState,
  Message,
  PastedImageSelection,
  SelectionButtonAnchor,
} from './types'
import {
  captureVideoThumbnail,
  fetchExampleImagePaths,
  formatIsabellaText,
  getAttachmentPreview,
  loadImageAsDataUrl,
  preloadFirstAutoraterExample,
  readImageFileAsDataUrl,
} from './utils'
import './App.css'

function App() {
  const [lessonInput, setLessonInput] = useState('')
  const [lessonMessages, setLessonMessages] = useState<Message[]>([])
  const [pendingPdfSelection, setPendingPdfSelection] = useState('')
  const [selectionButtonAnchor, setSelectionButtonAnchor] = useState<SelectionButtonAnchor | null>(null)
  const [pdfSelections, setPdfSelections] = useState<string[]>([])

  const [numPages, setNumPages] = useState(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [figures, setFigures] = useState<Figure[]>([])
  const [pendingFigureSelection, setPendingFigureSelection] = useState<FigureSelection | null>(null)
  const [figureSelections, setFigureSelections] = useState<FigureSelection[]>([])
  const [pastedImageSelections, setPastedImageSelections] = useState<PastedImageSelection[]>([])

  const [lessonState, setLessonState] = useState<LessonState>('idle')
  const [showChat, setShowChat] = useState(false)
  const [showPdf, setShowPdf] = useState(false)
  const [hasOpenedPdf, setHasOpenedPdf] = useState(false)
  const [appMode, setAppMode] = useState<AppMode>('friend')
  const [selectedLectureId, setSelectedLectureId] = useState(LECTURES[0].id)
  const [lectureThumbnails, setLectureThumbnails] = useState<Record<string, string>>({})

  const [autoraterMode, setAutoraterMode] = useState(false)
  const [autoraterStarted, setAutoraterStarted] = useState(false)
  const [autoraterLoading, setAutoraterLoading] = useState(false)
  const [exampleInput, setExampleInput] = useState('')
  const [exampleMessages, setExampleMessages] = useState<Message[]>([])
  const [exampleImagePaths, setExampleImagePaths] = useState<string[]>([])
  const [currentExampleIndex, setCurrentExampleIndex] = useState(0)
  const [currentExampleImage, setCurrentExampleImage] = useState('')
  const [exampleImageError, setExampleImageError] = useState('')

  const scrollRef = useRef<HTMLDivElement>(null)
  const pdfPanelRef = useRef<HTMLDivElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const pdfScrollTopRef = useRef(0)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const messageIdRef = useRef(0)

  const selectedLecture = LECTURES.find(lecture => lecture.id === selectedLectureId) ?? LECTURES[0]
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
    preloadFirstAutoraterExample().catch(error => {
      console.error('Error preloading first autorater example:', error)
    })
  }, [])

  useEffect(() => {
    let cancelled = false

    fetchExampleImagePaths()
      .then(images => {
        if (cancelled) return
        setExampleImagePaths(images)
        setCurrentExampleImage(prev => prev || images[0] || '')
        setExampleImageError(images.length > 0 ? '' : 'No example images were found.')
      })
      .catch(error => {
        if (!cancelled) {
          console.error('Failed to load example images:', error)
          setExampleImageError('Failed to load example images.')
        }
      })

    return () => {
      cancelled = true
    }
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
    const handleVideoShortcuts = (e: globalThis.KeyboardEvent) => {
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

  const handlePageClick = (e: MouseEvent<HTMLDivElement>, pageNumber: number) => {
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

  const handleChatPaste = async (e: ClipboardEvent<HTMLInputElement>) => {
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
      const response = await fetch(`${AUTORATER_API_URL}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_b64: imageB64 }),
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => response.statusText)
        throw new Error(`HTTP ${response.status}: ${detail}`)
      }
      const data = await response.json()
      setExampleMessages(prev => prev.map(m => (
        m.id === msgId ? { ...m, text: formatIsabellaText(data.opener, data.mode) } : m
      )))
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
    let imagePaths = exampleImagePaths

    setAutoraterMode(true)
    setAutoraterStarted(false)
    setExampleImageError('')
    setShowChat(true)
    setHasOpenedPdf(true)
    setShowPdf(true)
    clearPendingPdfSelection()
    setPendingFigureSelection(null)
    if (resetConversation) {
      resetExamplePage()
    }

    if (imagePaths.length === 0) {
      setAutoraterLoading(true)
      try {
        imagePaths = await fetchExampleImagePaths()
        setExampleImagePaths(imagePaths)
        setExampleImageError(imagePaths.length > 0 ? '' : 'No example images were found.')
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        console.error('Error loading examples:', msg)
        setExampleImageError(`Failed to load examples: ${msg}`)
        setExampleMessages(prev => [...prev, { role: 'assistant', text: `Failed to load examples: ${msg}` }])
        setAutoraterLoading(false)
        return
      }
      setAutoraterLoading(false)
    }

    const imagePath = imagePaths[exampleIndex]
    if (!imagePath) {
      setExampleImageError('No example image was found for this step.')
      setExampleMessages(prev => [...prev, { role: 'assistant', text: 'No example images were found.' }])
      return
    }

    setCurrentExampleIndex(exampleIndex)
    setCurrentExampleImage(imagePath)
    setExampleImageError('')

    try {
      const imageB64 = await loadImageAsDataUrl(imagePath)
      await startAutoraterSession(imageB64, `Loading Example ${exampleIndex + 1}...`)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error loading example:', msg)
      setExampleImageError(`Failed to prepare example: ${msg}`)
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
      const response = await fetch(`${AUTORATER_API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      setExampleMessages(prev => [...prev, { role: 'assistant', text: formatIsabellaText(data.reply, data.mode) }])
      if (data.next_opener) {
        setExampleMessages(prev => [...prev, {
          role: 'assistant',
          text: formatIsabellaText(data.next_opener, data.next_mode),
        }])
      }
      if (data.is_done) {
        const nextExampleIndex = currentExampleIndex + 1
        if (nextExampleIndex < exampleImagePaths.length) {
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
                  m.id === msgId ? { ...m, text: `Error: ${obj.error}` } : m
                ))
              }
            } catch {
              // Ignore non-JSON chunks such as heartbeats.
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
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

    const body: {
      message: string
      pdf_context?: string
      figure_context?: string
      figure_images?: string[]
      current_video_time?: number
    } = { message: messageText }

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
          return `Figure ${i + 1} - Label: ${s.figure.label}. Description: ${desc}`
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
      const response = await fetch(`${BACKEND_BASE_URL}/api/v1/chat/stream`, {
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
      setLessonMessages(prev => prev.map(m => (
        m.id === msgId ? { ...m, text: 'Failed to reach the assistant.' } : m
      )))
    }
  }

  const toggleTextbook = () => {
    setHasOpenedPdf(true)
    setShowPdf(prev => !prev)
  }

  const enterAutoraterMode = () => {
    videoRef.current?.pause()
    setLessonState('paused')
    void startExampleSession(0, true)
  }

  const endExampleSession = () => {
    setAutoraterMode(false)
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    resetExamplePage()
    setCurrentExampleIndex(0)
    setCurrentExampleImage(exampleImagePaths[0] || '')
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

  const handleChatInputChange = (value: string) => {
    if (autoraterMode) {
      setExampleInput(value)
    } else {
      setLessonInput(value)
    }
  }

  const handleChatInputEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    void sendMessage()
  }

  const lessonView = () => (
    <div className={`main-layout${autoraterMode ? ' autorater-screen' : ''}`}>
      <LessonStage
        selectedLecture={selectedLecture}
        lessonState={lessonState}
        autoraterMode={autoraterMode}
        videoRef={videoRef}
        onLessonStateChange={setLessonState}
        onOpenPlaylist={openPlaylist}
        onEnterAutoraterMode={enterAutoraterMode}
      />

      {hasOpenedPdf && (
        <PdfPanel
          autoraterMode={autoraterMode}
          showPdf={showPdf}
          numPages={numPages}
          containerWidth={containerWidth}
          pendingPdfSelection={pendingPdfSelection}
          pendingFigureSelection={pendingFigureSelection}
          selectionButtonAnchor={selectionButtonAnchor}
          pdfPanelRef={pdfPanelRef}
          pdfContainerRef={pdfContainerRef}
          pdfScrollRef={pdfScrollRef}
          onClose={() => setShowPdf(false)}
          onConfirmSelection={confirmSelection}
          onMouseUp={handleMouseUp}
          onPageClick={handlePageClick}
          onScrollTopChange={scrollTop => {
            pdfScrollTopRef.current = scrollTop
          }}
          onDocumentLoad={setNumPages}
        />
      )}

      {showChat && (
        <StudyChatPanel
          autoraterMode={autoraterMode}
          autoraterStarted={autoraterStarted}
          autoraterLoading={autoraterLoading}
          activeInput={activeInput}
          activeMessages={activeMessages}
          pdfSelections={pdfSelections}
          figureSelections={figureSelections}
          pastedImageSelections={pastedImageSelections}
          currentExampleIndex={currentExampleIndex}
          currentExampleImage={currentExampleImage}
          exampleImageError={exampleImageError}
          scrollRef={scrollRef}
          chatInputRef={chatInputRef}
          onClose={() => setShowChat(false)}
          onEndExampleSession={endExampleSession}
          onExampleImageLoad={() => setExampleImageError('')}
          onExampleImageError={() => setExampleImageError('This example image could not be displayed.')}
          onInputChange={handleChatInputChange}
          onInputPaste={handleChatPaste}
          onInputEnter={handleChatInputEnter}
          onSend={() => void sendMessage()}
          onRemovePdfSelection={idx => setPdfSelections(prev => prev.filter((_, i) => i !== idx))}
          onRemoveFigureSelection={idx => setFigureSelections(prev => prev.filter((_, i) => i !== idx))}
          onRemovePastedImageSelection={idx => setPastedImageSelections(prev => prev.filter((_, i) => i !== idx))}
        />
      )}

      {!autoraterMode && (
        <QuickActions
          showPdf={showPdf}
          showChat={showChat}
          onToggleTextbook={toggleTextbook}
          onToggleChat={toggleChat}
        />
      )}
    </div>
  )

  const viewRegistry: Record<AppMode, () => ReactNode> = {
    friend: () => (
      <div className="main-layout">
        <FriendView onExit={openPlaylist} />
      </div>
    ),
    playlist: () => (
      <PlaylistView
        lectures={LECTURES}
        selectedLectureId={selectedLectureId}
        lectureThumbnails={lectureThumbnails}
        onOpenLecture={openLecture}
      />
    ),
    lesson: lessonView,
  }

  return viewRegistry[appMode]()
}

export default App
