import { useState, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import './App.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

interface Message {
  role: 'user' | 'assistant';
  text: string;
  id?: number;
}

interface Figure {
  id: string;
  page: number;
  bbox: { x: number; y: number; x2: number; y2: number };
  label: string;
  description: string;
}

const FIGURES_STORAGE_KEY = 'home_schooling_figures_v1'

type LessonState = 'idle' | 'playing' | 'paused' | 'question'

function App() {
  // 채팅
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [pdfSelection, setPdfSelection] = useState('')

  // PDF 뷰어
  const [numPages, setNumPages] = useState(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [figures, setFigures] = useState<Figure[]>(() => {
    const stored = localStorage.getItem(FIGURES_STORAGE_KEY)
    if (stored) {
      try { return JSON.parse(stored) as Figure[] } catch { /* fall through */ }
    }
    return []
  })
  const [clickedFigure, setClickedFigure] = useState<Figure | null>(null)
  const [clickedFigureImage, setClickedFigureImage] = useState<string | null>(null)

  // Figure 편집 모드
  const [editMode, setEditMode] = useState(false)
  const [drawing, setDrawing] = useState<{ pageNum: number; startX: number; startY: number; curX: number; curY: number } | null>(null)
  const [pendingFigure, setPendingFigure] = useState<{ page: number; bbox: { x: number; y: number; x2: number; y2: number } } | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editDescription, setEditDescription] = useState('')

  // 수업 재생
  const [lessonState, setLessonState] = useState<LessonState>('idle')

  const scrollRef = useRef<HTMLDivElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const typewriterRef = useRef<number | null>(null)

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // PDF 컨테이너 너비 감지
  useEffect(() => {
    if (!pdfContainerRef.current) return
    const observer = new ResizeObserver(entries => {
      setContainerWidth(entries[0].contentRect.width)
    })
    observer.observe(pdfContainerRef.current)
    return () => observer.disconnect()
  }, [])

  // figures.json 로드 (localStorage 비었을 때만 seed로 사용)
  useEffect(() => {
    if (localStorage.getItem(FIGURES_STORAGE_KEY)) return
    fetch('/assets/figures.json')
      .then(r => r.json())
      .then(setFigures)
      .catch(console.error)
  }, [])

  // figures 변경 시 localStorage 자동 저장
  useEffect(() => {
    localStorage.setItem(FIGURES_STORAGE_KEY, JSON.stringify(figures))
  }, [figures])

  // 언마운트 시 타이프라이터 정리
  useEffect(() => {
    return () => {
      if (typewriterRef.current !== null) cancelAnimationFrame(typewriterRef.current)
    }
  }, [])

  // ── Figure 편집 ──────────────────────────────────────────────────
  const handleDrawMouseDown = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    if (!editMode) return
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setDrawing({ pageNum, startX: x, startY: y, curX: x, curY: y })
  }

  const handleDrawMouseMove = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    if (!editMode || !drawing || drawing.pageNum !== pageNum) return
    const rect = e.currentTarget.getBoundingClientRect()
    setDrawing(prev => prev ? { ...prev, curX: e.clientX - rect.left, curY: e.clientY - rect.top } : null)
  }

  const handleDrawMouseUp = (e: React.MouseEvent<HTMLDivElement>, pageNum: number) => {
    if (!editMode || !drawing || drawing.pageNum !== pageNum) return
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

  // ── PDF Figure 클릭 (일반 모드) ──────────────────────────────────
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
    if (!found) return

    setClickedFigure(found)

    // PDF canvas에서 bbox 영역을 잘라 base64 PNG로 저장
    const sourceCanvas = e.currentTarget.querySelector('canvas') as HTMLCanvasElement | null
    if (!sourceCanvas) {
      setClickedFigureImage(null)
      return
    }
    const renderScale = sourceCanvas.width / (containerWidth)
    const sx = found.bbox.x * scale * renderScale
    const sy = found.bbox.y * scale * renderScale
    const sw = (found.bbox.x2 - found.bbox.x) * scale * renderScale
    const sh = (found.bbox.y2 - found.bbox.y) * scale * renderScale
    const out = document.createElement('canvas')
    out.width = Math.max(1, Math.round(sw))
    out.height = Math.max(1, Math.round(sh))
    const ctx = out.getContext('2d')
    if (!ctx) {
      setClickedFigureImage(null)
      return
    }
    ctx.drawImage(sourceCanvas, sx, sy, sw, sh, 0, 0, out.width, out.height)
    setClickedFigureImage(out.toDataURL('image/png'))
  }

  // ── PDF 텍스트 선택 ──────────────────────────────────────────────
  const handleMouseUp = () => {
    if (editMode) return
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) {
      setPdfSelection('')
      return
    }
    setPdfSelection(selection.toString().trim())
  }

  // ── 채팅 전송 ────────────────────────────────────────────────────
  const sendMessage = async () => {
    const messageText = input.trim() || ((pdfSelection || clickedFigure) ? 'Explain this.' : '')
    if (!messageText) return

    setMessages(prev => [...prev, { role: 'user', text: messageText }])
    setInput('')

    const body: { message: string; pdf_context?: string; figure_context?: string; figure_image?: string; current_video_time?: number } = { message: messageText }
    if (pdfSelection) body.pdf_context = pdfSelection
    if (clickedFigure) {
      const desc = clickedFigure.description ? clickedFigure.description : '(no description)'
      body.figure_context = `Label: ${clickedFigure.label}. Description: ${desc}`
      if (clickedFigureImage) body.figure_image = clickedFigureImage
    }
    if (videoRef.current && videoRef.current.currentTime > 0) {
      body.current_video_time = videoRef.current.currentTime
    }

    setPdfSelection('')
    setClickedFigure(null)
    setClickedFigureImage(null)
    window.getSelection()?.removeAllRanges()

    try {
      const response = await fetch('http://localhost:8000/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json()

      const msgId = Date.now()
      setMessages(prev => [...prev, { role: 'assistant', text: '', id: msgId }])

      fetchTTS(data.reply)
        .then(url => {
          const audio = new Audio(url)
          audio.onplay = () => startTypewriterAnimation(audio, data.reply, msgId)
          audio.onended = () => {
            URL.revokeObjectURL(url)
            setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: data.reply } : m))
          }
          audio.play()
        })
        .catch(console.error)
    } catch (error) {
      console.error('Error:', error)
    }
  }

  // ── 타이프라이터 ─────────────────────────────────────────────────
  const startTypewriterAnimation = (audio: HTMLAudioElement, content: string, msgId: number, pauseTime: number = 0) => {
    if (typewriterRef.current !== null) {
      cancelAnimationFrame(typewriterRef.current)
      typewriterRef.current = null
    }

    let lastUpdate = 0
    const tick = (timestamp: number) => {
      if (audio.paused || audio.ended) {
        if (audio.ended) {
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: content } : m))
          typewriterRef.current = null
        }
        return
      }
      if (timestamp - lastUpdate > 50) {
        lastUpdate = timestamp
        const elapsed = audio.currentTime - pauseTime
        const remaining = audio.duration > 0 ? audio.duration - pauseTime : 1
        const ratio = Math.max(0, Math.min(elapsed / remaining, 1))
        const charCount = Math.ceil(ratio * content.length)
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: content.slice(0, charCount) } : m))
      }
      typewriterRef.current = requestAnimationFrame(tick)
    }
    typewriterRef.current = requestAnimationFrame(tick)
  }

  // ── 수업 재생 (영상) ─────────────────────────────────────────────
  const fetchTTS = async (text: string): Promise<string> => {
    const res = await fetch('http://localhost:8000/api/v1/lesson/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    const blob = await res.blob()
    return URL.createObjectURL(blob)
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

  const askQuestion = () => {
    videoRef.current?.pause()
    setLessonState('question')
    setTimeout(() => chatInputRef.current?.focus(), 100)
  }

  const handlePlayBtn = () => {
    if (lessonState === 'idle') startLesson()
    else if (lessonState === 'playing') pauseLesson()
    else if (lessonState === 'paused' || lessonState === 'question') resumeLesson()
  }

  const playBtnLabel = () => {
    if (lessonState === 'playing') return '⏸'
    return '▶'
  }

  return (
    <div className="main-layout">

      {/* ================= 왼쪽: PDF 영역 ================= */}
      <div className="pdf-section" ref={pdfContainerRef} onMouseUp={handleMouseUp}>

        {/* Figure 편집 툴바 */}
        <div className="figure-toolbar">
          <button
            className={`btn-figure-edit ${editMode ? 'active' : ''}`}
            onClick={() => { setEditMode(prev => !prev); setDrawing(null); setPendingFigure(null) }}
          >
            {editMode ? '✏️ Editing — click to exit' : '+ Add Figure'}
          </button>
          {editMode && (
            <>
              <span className="figure-edit-hint">Drag to draw a box</span>
              <button className="btn-export" onClick={exportFigures}>⬇ Export JSON</button>
            </>
          )}
        </div>

        <div className="pdf-scroll" style={{ height: editMode ? 'calc(100% - 44px)' : 'calc(100% - 44px)' }}>
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
                    cursor: editMode ? 'crosshair' : 'default',
                    userSelect: editMode ? 'none' : 'auto',
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

                  {/* 편집 모드: 기존 Figure 오버레이 */}
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
                      }}
                    >
                      <div className="figure-overlay-label">
                        <span>{f.label}</span>
                        <button
                          className="figure-overlay-delete"
                          onClick={e => { e.stopPropagation(); deleteFigure(f.id) }}
                        >✕</button>
                      </div>
                    </div>
                  ))}

                  {/* 드래그 중 미리보기 */}
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
                </div>
              )
            })}
          </Document>
        </div>
      </div>

      {/* ================= Figure 추가 다이얼로그 ================= */}
      {pendingFigure && (
        <div
          className="figure-dialog-overlay"
          onClick={e => { if (e.target === e.currentTarget) setPendingFigure(null) }}
        >
          <div className="figure-dialog">
            <h3>Add Figure</h3>
            <p className="figure-dialog-meta">
              Page {pendingFigure.page} &nbsp;|&nbsp;
              ({pendingFigure.bbox.x}, {pendingFigure.bbox.y}) ~ ({pendingFigure.bbox.x2}, {pendingFigure.bbox.y2})
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
              Description <span style={{ fontWeight: 'normal', color: '#888' }}>(included in the prompt)</span>
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

      {/* ================= 오른쪽: 선생님 + 채팅 영역 ================= */}
      <div className="right-section">

        {/* 오른쪽 위: 선생님 화면 */}
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

          <div className="lesson-buttons">
            <button className="btn-play" onClick={handlePlayBtn}>
              {playBtnLabel()}
            </button>
            <button
              className="btn-question"
              onClick={askQuestion}
              disabled={lessonState === 'idle' || lessonState === 'question'}
            >
              ❓
            </button>
          </div>
        </div>

        {/* 오른쪽 아래: 채팅 */}
        <div className="chat-view">
          <div className="chat-window" ref={scrollRef}>
            {messages.map((msg, idx) => (
              <div key={idx} className={`bubble ${msg.role}`}>
                {msg.text}
              </div>
            ))}
          </div>

          {clickedFigure && (
            <div className="pdf-selection-bar">
              <span>🖼 {clickedFigure.label} clicked</span>
              <button onClick={() => setClickedFigure(null)}>✕</button>
            </div>
          )}

          {pdfSelection && (
            <div className="pdf-selection-bar">
              <span>📄 Dragged</span>
              <button onClick={() => { setPdfSelection(''); window.getSelection()?.removeAllRanges() }}>✕</button>
            </div>
          )}

          <div className="input-area">
            <input
              ref={chatInputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder={lessonState === 'question' ? 'Type your question...' : 'Type a message...'}
            />
            <button onClick={sendMessage}>Send</button>
          </div>
        </div>
      </div>

    </div>
  )
}

export default App
