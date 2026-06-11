import { useState, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { ArrowLeft, FastForward, FileText, MessageCircle, Pause, Play, Users, X } from 'lucide-react'
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

interface Message {
  role: 'user' | 'assistant'
  text: string
  id?: number
}

interface Figure {
  id: string
  page: number
  bbox: { x: number; y: number; x2: number; y2: number }
  label: string
  description: string
}

const FIGURES_STORAGE_KEY = 'home_schooling_figures_v1'

type LessonState = 'idle' | 'playing' | 'paused' | 'question'

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [pendingPdfSelection, setPendingPdfSelection] = useState('')
  const [pdfSelections, setPdfSelections] = useState<string[]>([])

  const [numPages, setNumPages] = useState(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [figures, setFigures] = useState<Figure[]>(() => {
    const stored = localStorage.getItem(FIGURES_STORAGE_KEY)
    if (stored) {
      try {
        return JSON.parse(stored) as Figure[]
      } catch {
        // Fall back to bundled figures.
      }
    }
    return []
  })
  const [pendingFigureSelection, setPendingFigureSelection] = useState<{ figure: Figure; image: string | null } | null>(null)
  const [figureSelections, setFigureSelections] = useState<{ figure: Figure; image: string | null }[]>([])

  const [editMode, setEditMode] = useState(false)
  const [addFigureMode, setAddFigureMode] = useState(false)
  const [drawing, setDrawing] = useState<{ pageNum: number; startX: number; startY: number; curX: number; curY: number } | null>(null)
  const [pendingFigure, setPendingFigure] = useState<{ page: number; bbox: { x: number; y: number; x2: number; y2: number } } | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editDescription, setEditDescription] = useState('')

  const [lessonState, setLessonState] = useState<LessonState>('idle')
  const [showChat, setShowChat] = useState(false)
  const [showPdf, setShowPdf] = useState(false)
  const [hasOpenedPdf, setHasOpenedPdf] = useState(false)
  const [appMode, setAppMode] = useState<'lesson' | 'friend'>('lesson')

  // Autorater (Isabella) mode state
  const [autoraterMode, setAutoraterMode] = useState(false)
  const [autoraterStarted, setAutoraterStarted] = useState(false)
  const [autoraterLoading, setAutoraterLoading] = useState(false)
  const [autoraterCaptureDraw, setAutoraterCaptureDraw] = useState<{
    pageNum: number; startX: number; startY: number; curX: number; curY: number
  } | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const messageIdRef = useRef(0)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, showChat])

  useEffect(() => {
    if (!showPdf || !pdfContainerRef.current) return
    const observer = new ResizeObserver(entries => {
      setContainerWidth(Math.max(320, Math.floor(entries[0].contentRect.width)))
    })
    observer.observe(pdfContainerRef.current)
    return () => observer.disconnect()
  }, [showPdf])

  useEffect(() => {
    if (!showChat) return
    const timeout = window.setTimeout(() => chatInputRef.current?.focus(), 100)
    return () => window.clearTimeout(timeout)
  }, [showChat])

  useEffect(() => {
    if (localStorage.getItem(FIGURES_STORAGE_KEY)) return
    fetch('/assets/figures.json')
      .then(r => r.json())
      .then(setFigures)
      .catch(console.error)
  }, [])

  useEffect(() => {
    localStorage.setItem(FIGURES_STORAGE_KEY, JSON.stringify(figures))
  }, [figures])

  const handleDrawMouseDown = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    // Autorater capture mode: free-drag region selection
    if (autoraterMode && !autoraterStarted) {
      e.preventDefault()
      const rect = e.currentTarget.getBoundingClientRect()
      setAutoraterCaptureDraw({
        pageNum,
        startX: e.clientX - rect.left,
        startY: e.clientY - rect.top,
        curX: e.clientX - rect.left,
        curY: e.clientY - rect.top,
      })
      return
    }
    if (!editMode || !addFigureMode) return
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    setDrawing({
      pageNum,
      startX: e.clientX - rect.left,
      startY: e.clientY - rect.top,
      curX: e.clientX - rect.left,
      curY: e.clientY - rect.top,
    })
  }

  const handleDrawMouseMove = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    if (autoraterMode && !autoraterStarted && autoraterCaptureDraw && autoraterCaptureDraw.pageNum === pageNum) {
      const rect = e.currentTarget.getBoundingClientRect()
      setAutoraterCaptureDraw(prev => prev ? { ...prev, curX: e.clientX - rect.left, curY: e.clientY - rect.top } : null)
      return
    }
    if (!editMode || !addFigureMode || !drawing || drawing.pageNum !== pageNum) return
    const rect = e.currentTarget.getBoundingClientRect()
    setDrawing(prev => prev ? { ...prev, curX: e.clientX - rect.left, curY: e.clientY - rect.top } : null)
  }

  const handleDrawMouseUp = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    // Autorater capture: crop and send the drawn region as image
    if (autoraterMode && !autoraterStarted && autoraterCaptureDraw && autoraterCaptureDraw.pageNum === pageNum) {
      const draw = autoraterCaptureDraw
      setAutoraterCaptureDraw(null)
      const rect = e.currentTarget.getBoundingClientRect()
      const curX = e.clientX - rect.left
      const curY = e.clientY - rect.top
      if (Math.abs(curX - draw.startX) < 10 || Math.abs(curY - draw.startY) < 10) return

      const sourceCanvas = e.currentTarget.querySelector('canvas') as HTMLCanvasElement | null
      if (!sourceCanvas) return
      const renderScale = sourceCanvas.width / containerWidth
      const sx = Math.min(draw.startX, curX) * renderScale
      const sy = Math.min(draw.startY, curY) * renderScale
      const sw = Math.abs(curX - draw.startX) * renderScale
      const sh = Math.abs(curY - draw.startY) * renderScale
      const out = document.createElement('canvas')
      out.width = Math.max(1, Math.round(sw))
      out.height = Math.max(1, Math.round(sh))
      const ctx = out.getContext('2d')
      if (!ctx) return
      ctx.drawImage(sourceCanvas, sx, sy, sw, sh, 0, 0, out.width, out.height)
      startAutoraterSession(out.toDataURL('image/png'))
      return
    }

    if (!editMode || !addFigureMode || !drawing || drawing.pageNum !== pageNum) return
    const rect = e.currentTarget.getBoundingClientRect()
    const scale = containerWidth / 595.3
    const curX = e.clientX - rect.left
    const curY = e.clientY - rect.top

    if (Math.abs(curX - drawing.startX) < 10 || Math.abs(curY - drawing.startY) < 10) {
      setDrawing(null)
      return
    }

    const round = (n: number) => Math.round(n * 10) / 10
    const bbox = {
      x: round(Math.min(drawing.startX, curX) / scale),
      y: round(Math.min(drawing.startY, curY) / scale),
      x2: round(Math.max(drawing.startX, curX) / scale),
      y2: round(Math.max(drawing.startY, curY) / scale),
    }
    setDrawing(null)
    setEditLabel(`Figure ${figures.length + 1}`)
    setEditDescription('')
    setPendingFigure({ page: pageNum, bbox })
  }

  const confirmAddFigure = () => {
    if (!pendingFigure || !editLabel.trim()) return
    const newFig: Figure = {
      id: `fig${Date.now()}`,
      page: pendingFigure.page,
      bbox: pendingFigure.bbox,
      label: editLabel.trim(),
      description: editDescription.trim(),
    }
    setFigures(prev => [...prev, newFig])
    setPendingFigure(null)
  }

  const deleteFigure = (id: string) => {
    setFigures(prev => prev.filter(f => f.id !== id))
  }

  const exportFigures = () => {
    const json = JSON.stringify(figures, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'figures.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handlePageClick = (e: React.MouseEvent<HTMLDivElement>, pageNumber: number) => {
    if (editMode) return
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
  }

  const handleMouseUp = () => {
    if (editMode) return
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) {
      setPendingPdfSelection('')
      return
    }
    setPendingPdfSelection(selection.toString().trim())
  }

  const confirmSelection = () => {
    const text = pendingPdfSelection.trim()
    if (text) {
      setPdfSelections(prev => [...prev, text])
      setPendingPdfSelection('')
      window.getSelection()?.removeAllRanges()
    }
    if (pendingFigureSelection) {
      setFigureSelections(prev => [...prev, pendingFigureSelection])
      setPendingFigureSelection(null)
    }
  }

  const removePdfSelectionAt = (idx: number) => {
    setPdfSelections(prev => prev.filter((_, i) => i !== idx))
  }

  const removeFigureSelectionAt = (idx: number) => {
    setFigureSelections(prev => prev.filter((_, i) => i !== idx))
  }

  const startAutoraterSession = async (imageB64: string) => {
    setAutoraterLoading(true)
    const msgId = ++messageIdRef.current
    setMessages(prev => [...prev, { role: 'assistant', text: 'Analyzing problem...', id: msgId }])

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
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: `Isabella: ${data.opener}` } : m))
      setAutoraterStarted(true)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error starting autorater:', msg)
      setMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, text: `Failed to start: ${msg}` } : m
      ))
    } finally {
      setAutoraterLoading(false)
    }
  }

  const sendAutoraterMessage = async () => {
    const messageText = input.trim()
    if (!messageText || autoraterLoading) return

    setMessages(prev => [...prev, { role: 'user', text: messageText }])
    setInput('')
    setAutoraterLoading(true)

    try {
      const response = await fetch('http://localhost:8000/api/v1/autorater/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      setMessages(prev => [...prev, { role: 'assistant', text: `Isabella: ${data.reply}` }])
      if (data.next_opener) {
        setMessages(prev => [...prev, { role: 'assistant', text: `Isabella: ${data.next_opener}` }])
      }
      if (data.is_done) {
        setAutoraterMode(false)
        setAutoraterStarted(false)
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error in autorater chat:', msg)
      setMessages(prev => [...prev, { role: 'assistant', text: `Error: ${msg}` }])
    } finally {
      setAutoraterLoading(false)
    }
  }

  const sendMessage = async () => {
    if (autoraterStarted && autoraterMode) {
      await sendAutoraterMessage()
      return
    }
    const hasContext = pdfSelections.length > 0 || figureSelections.length > 0
    const messageText = input.trim() || (hasContext ? 'Explain this.' : '')
    if (!messageText) return

    setShowChat(true)
    setMessages(prev => [...prev, { role: 'user', text: messageText }])
    setInput('')

    const body: { message: string; pdf_context?: string; figure_context?: string; figure_images?: string[]; current_video_time?: number } = { message: messageText }
    if (pdfSelections.length > 0) {
      body.pdf_context = pdfSelections
        .map((s, i) => `Passage ${i + 1}:\n"""\n${s}\n"""`)
        .join('\n\n')
    }
    if (figureSelections.length > 0) {
      body.figure_context = figureSelections
        .map((s, i) => {
          const desc = s.figure.description ? s.figure.description : '(no description)'
          return `Figure ${i + 1} — Label: ${s.figure.label}. Description: ${desc}`
        })
        .join('\n\n')
      const images = figureSelections
        .map(s => s.image)
        .filter((img): img is string => !!img)
      if (images.length > 0) body.figure_images = images
    }
    if (videoRef.current && videoRef.current.currentTime > 0) {
      body.current_video_time = videoRef.current.currentTime
    }

    setPdfSelections([])
    setPendingPdfSelection('')
    setFigureSelections([])
    setPendingFigureSelection(null)
    window.getSelection()?.removeAllRanges()

    const msgId = ++messageIdRef.current
    setMessages(prev => [...prev, { role: 'assistant', text: '', id: msgId }])

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
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: '⚠️ Failed to reach the assistant.' } : m))
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
                setMessages(prev => prev.map(m =>
                  m.id === msgId ? { ...m, text: m.text + obj.delta } : m
                ))
              } else if (obj.error) {
                setMessages(prev => prev.map(m =>
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

  const startLesson = () => {
    videoRef.current?.play()
    setLessonState('playing')
  }

  const pauseLesson = () => {
    videoRef.current?.pause()
    setLessonState('paused')
  }

  const resumeLesson = () => {
    videoRef.current?.play()
    setLessonState('playing')
  }

  const showTextbook = () => {
    setHasOpenedPdf(true)
    setShowPdf(true)
  }

  const toggleTextbook = () => {
    setHasOpenedPdf(true)
    setShowPdf(prev => !prev)
  }

  const enterAutoraterMode = () => {
    // 2-1: Open chat without clearing history
    setShowChat(true)
    // 2-2: Stop the video and open PDF in drag-select capture mode
    if (videoRef.current) {
      videoRef.current.pause()
    }
    setLessonState('paused')
    showTextbook()
    setEditMode(false)
    setAutoraterMode(true)
    setAutoraterStarted(false)
    setAutoraterCaptureDraw(null)
  }

  const handlePlayBtn = () => {
    if (lessonState === 'idle') startLesson()
    else if (lessonState === 'playing') pauseLesson()
    else if (lessonState === 'paused' || lessonState === 'question') resumeLesson()
  }

  const playBtnIcon = () => {
    if (lessonState === 'playing') return <Pause size={20} strokeWidth={2.6} />
    return <Play size={20} strokeWidth={2.6} fill="currentColor" />
  }

  if (appMode === 'friend') {
    return (
      <div className="main-layout">
        <FriendView onExit={() => setAppMode('lesson')} />
      </div>
    )
  }

  return (
    <div className="main-layout">
      <div className="teacher-view">
        <video
          ref={videoRef}
          src="/assets/video.mp4"
          className="character-video"
          onEnded={() => setLessonState('paused')}
          playsInline
        />

        {lessonState === 'question' && (
          <div className="lesson-progress">Asking question</div>
        )}

        <div className="lesson-buttons" aria-label="Lesson controls">
          <button className="btn-play" onClick={handlePlayBtn} aria-label={lessonState === 'playing' ? 'Pause lesson' : 'Play lesson'}>
            {playBtnIcon()}
          </button>
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

      {hasOpenedPdf && (
        <div className={`floating-panel pdf-panel${showPdf ? '' : ' pdf-panel-hidden'}`} aria-hidden={!showPdf}>
          <div className="panel-header">
            <span>Textbook</span>
            <button className="panel-close" onClick={() => setShowPdf(false)} aria-label="Close textbook">
              <X size={18} />
            </button>
          </div>

          {!autoraterMode && (pendingPdfSelection || pendingFigureSelection) && (
            <button
              className="btn-pdf-select"
              onClick={confirmSelection}
              title="Add this selection to the chat prompt"
            >
              + Select
            </button>
          )}

          <div className="pdf-section" ref={pdfContainerRef} onMouseUp={handleMouseUp}>
            {autoraterMode && !autoraterStarted ? (
              <div className="autorater-capture-toolbar">
                <span className="autorater-capture-hint">
                  {autoraterLoading ? 'Analyzing…' : 'Draw a box around an example problem to start practicing with Isabella'}
                </span>
              </div>
            ) : (
              <div className="figure-toolbar">
                {!editMode ? (
                  <button
                    className="btn-figure-edit"
                    onClick={() => setEditMode(true)}
                  >
                    Edit Figures
                  </button>
                ) : (
                  <>
                    <button
                      className="btn-figure-edit btn-figure-back"
                      onClick={() => { setEditMode(false); setAddFigureMode(false); setDrawing(null); setPendingFigure(null) }}
                      title="Exit edit mode"
                      aria-label="Exit edit mode"
                    >
                      <ArrowLeft size={16} />
                    </button>
                    <button
                      className={`btn-figure-edit ${addFigureMode ? 'active' : ''}`}
                      onClick={() => { setAddFigureMode(prev => !prev); setDrawing(null) }}
                    >
                      {addFigureMode ? 'Adding…' : '+ Add Figure'}
                    </button>
                    {addFigureMode && (
                      <span className="figure-edit-hint">Drag to draw a box</span>
                    )}
                    <button className="btn-export" onClick={exportFigures}>Export JSON</button>
                  </>
                )}
              </div>
            )}

            <div className="pdf-scroll">
              <Document
                file="/assets/Chapter4.pdf"
                onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              >
                {Array.from({ length: numPages }, (_, i) => {
                  const pageNum = i + 1
                  const scale = containerWidth / 595.3
                  const pageFigs = figures.filter(f => f.page === pageNum)
                  return (
                    <div
                      key={pageNum}
                      style={{
                        position: 'relative',
                        cursor: (editMode && addFigureMode) || (autoraterMode && !autoraterStarted) ? 'crosshair' : 'default',
                        userSelect: (editMode && addFigureMode) || (autoraterMode && !autoraterStarted) ? 'none' : 'auto',
                      }}
                      onClick={e => handlePageClick(e, pageNum)}
                      onMouseDown={e => handleDrawMouseDown(e, pageNum)}
                      onMouseMove={e => handleDrawMouseMove(e, pageNum)}
                      onMouseUp={e => handleDrawMouseUp(e, pageNum)}
                    >
                      <Page
                        pageNumber={pageNum}
                        width={containerWidth}
                        renderTextLayer
                        renderAnnotationLayer={false}
                      />

                      {editMode && pageFigs.map(f => (
                        <div
                          key={f.id}
                          style={{
                            position: 'absolute',
                            left: f.bbox.x * scale,
                            top: f.bbox.y * scale,
                            width: (f.bbox.x2 - f.bbox.x) * scale,
                            height: (f.bbox.y2 - f.bbox.y) * scale,
                            border: '2px solid #e53935',
                            backgroundColor: 'rgba(229,57,53,0.08)',
                            boxSizing: 'border-box',
                            zIndex: 5,
                          }}
                        >
                          <div className="figure-overlay-label">
                            <span>{f.label}</span>
                            <button
                              className="figure-overlay-delete"
                              onClick={e => { e.stopPropagation(); deleteFigure(f.id) }}
                              onMouseDown={e => e.stopPropagation()}
                              title="Delete figure"
                              aria-label="Delete figure"
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      ))}

                      {!editMode && !autoraterMode && pendingFigureSelection && pendingFigureSelection.figure.page === pageNum && (
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

                      {editMode && drawing && drawing.pageNum === pageNum && (
                        <div
                          style={{
                            position: 'absolute',
                            left: Math.min(drawing.startX, drawing.curX),
                            top: Math.min(drawing.startY, drawing.curY),
                            width: Math.abs(drawing.curX - drawing.startX),
                            height: Math.abs(drawing.curY - drawing.startY),
                            border: '2px dashed #1565c0',
                            backgroundColor: 'rgba(21,101,192,0.1)',
                            pointerEvents: 'none',
                            boxSizing: 'border-box',
                          }}
                        />
                      )}

                      {autoraterMode && !autoraterStarted && autoraterCaptureDraw && autoraterCaptureDraw.pageNum === pageNum && (
                        <div
                          style={{
                            position: 'absolute',
                            left: Math.min(autoraterCaptureDraw.startX, autoraterCaptureDraw.curX),
                            top: Math.min(autoraterCaptureDraw.startY, autoraterCaptureDraw.curY),
                            width: Math.abs(autoraterCaptureDraw.curX - autoraterCaptureDraw.startX),
                            height: Math.abs(autoraterCaptureDraw.curY - autoraterCaptureDraw.startY),
                            border: '2px dashed #16a34a',
                            backgroundColor: 'rgba(22,163,74,0.12)',
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

      {pendingFigure && (
        <div
          className="figure-dialog-overlay"
          onClick={e => { if (e.target === e.currentTarget) setPendingFigure(null) }}
        >
          <div className="figure-dialog">
            <h3>Add Figure</h3>
            <p className="figure-dialog-meta">
              Page {pendingFigure.page} | ({pendingFigure.bbox.x}, {pendingFigure.bbox.y}) - ({pendingFigure.bbox.x2}, {pendingFigure.bbox.y2})
            </p>
            <label className="figure-dialog-label">
              Label
              <input
                value={editLabel}
                onChange={e => setEditLabel(e.target.value)}
                placeholder="e.g. Figure 1"
                autoFocus
                onKeyDown={e => e.key === 'Enter' && confirmAddFigure()}
              />
            </label>
            <label className="figure-dialog-label">
              Description <span className="optional-label">(included in the prompt)</span>
              <textarea
                value={editDescription}
                onChange={e => setEditDescription(e.target.value)}
                placeholder="e.g. Coordinate plane with points A, B, C plotted"
                rows={3}
              />
            </label>
            <div className="figure-dialog-buttons">
              <button onClick={() => setPendingFigure(null)}>Cancel</button>
              <button
                className="btn-confirm"
                onClick={confirmAddFigure}
                disabled={!editLabel.trim()}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}

      {showChat && (
        <div className="floating-panel chat-panel">
          <div className="panel-header">
            <span>{autoraterMode ? 'Isabella — Practice' : 'Chat'}</span>
            <button className="panel-close" onClick={() => setShowChat(false)} aria-label="Close chat">
              <X size={18} />
            </button>
          </div>

          <div className="chat-view">
            <div className="chat-window" ref={scrollRef}>
              {messages.map((msg, idx) => (
                <div key={idx} className={`bubble ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <div className="markdown-body">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {msg.text}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    msg.text
                  )}
                </div>
              ))}
            </div>

            {autoraterMode && !autoraterStarted && (
              <div className="autorater-chat-hint">
                Draw a box around a problem in the textbook to begin.
              </div>
            )}

            {!autoraterMode && (pdfSelections.length > 0 || figureSelections.length > 0) && (
              <div className="pdf-selection-list">
                {pdfSelections.map((sel, i) => (
                  <div key={`p-${i}`} className="pdf-selection-chip" title={sel}>
                    <span className="pdf-selection-chip-label">
                      ¶{i + 1} {sel.length > 40 ? sel.slice(0, 40) + '…' : sel}
                    </span>
                    <button
                      className="pdf-selection-chip-remove"
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
                    className="pdf-selection-chip figure-selection-chip"
                    title={sel.figure.description || sel.figure.label}
                  >
                    <span className="pdf-selection-chip-label">
                      Fig · {sel.figure.label}
                    </span>
                    <button
                      className="pdf-selection-chip-remove"
                      onClick={() => removeFigureSelectionAt(i)}
                      aria-label="Remove figure"
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
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder={
                  autoraterMode && !autoraterStarted
                    ? 'Select a problem from the textbook first…'
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
          onClick={() => setShowChat(prev => !prev)}
          aria-label={showChat ? 'Hide chat' : 'Show chat'}
          title={showChat ? 'Hide chat' : 'Show chat'}
        >
          <MessageCircle size={22} />
        </button>
        <button
          className="quick-action"
          onClick={() => setAppMode('friend')}
          aria-label="Chat with Jiho"
          title="Chat with Jiho"
        >
          <Users size={22} />
        </button>
      </div>
    </div>
  )
}

export default App
