import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type MouseEvent,
} from 'react'
import type {
  ChatAttachment,
  Figure,
  FigureSelection,
  PastedImageSelection,
  SelectionButtonAnchor,
} from '../../../types'
import { getAttachmentPreview, readImageFileAsDataUrl } from '../../../utils'

interface UsePdfSelectionViewModelParams {
  showPdf: boolean
  onContextQueued: () => void
}

export const usePdfSelectionViewModel = ({
  showPdf,
  onContextQueued,
}: UsePdfSelectionViewModelParams) => {
  const [pendingPdfSelection, setPendingPdfSelection] = useState('')
  const [selectionButtonAnchor, setSelectionButtonAnchor] = useState<SelectionButtonAnchor | null>(null)
  const [pdfSelections, setPdfSelections] = useState<string[]>([])

  const [numPages, setNumPages] = useState(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [figures, setFigures] = useState<Figure[]>([])
  const [pendingFigureSelection, setPendingFigureSelection] = useState<FigureSelection | null>(null)
  const [figureSelections, setFigureSelections] = useState<FigureSelection[]>([])
  const [pastedImageSelections, setPastedImageSelections] = useState<PastedImageSelection[]>([])

  const pdfPanelRef = useRef<HTMLDivElement>(null)
  const pdfContainerRef = useRef<HTMLDivElement>(null)
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const pdfScrollTopRef = useRef(0)

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

  const resetScroll = () => {
    pdfScrollTopRef.current = 0
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
    if (!showPdf || !pdfContainerRef.current) return
    const observer = new ResizeObserver(entries => {
      setContainerWidth(Math.max(320, Math.floor(entries[0].contentRect.width)))
    })
    observer.observe(pdfContainerRef.current)
    return () => observer.disconnect()
  }, [showPdf])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (pdfScrollRef.current) {
        pdfScrollRef.current.scrollTop = pdfScrollTopRef.current
      }
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [showPdf])

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
    onContextQueued()
  }

  const handleChatPaste = async (e: ClipboardEvent<HTMLInputElement>) => {
    const imageFiles = Array.from(e.clipboardData.files).filter(file => file.type.startsWith('image/'))
    if (imageFiles.length === 0) return

    e.preventDefault()
    try {
      const images = await Promise.all(imageFiles.map(readImageFileAsDataUrl))
      setPastedImageSelections(prev => [...prev, ...images])
      onContextQueued()
    } catch (error) {
      console.error('Failed to read pasted image:', error)
    }
  }

  return {
    pendingPdfSelection,
    selectionButtonAnchor,
    pdfSelections,
    numPages,
    containerWidth,
    pendingFigureSelection,
    figureSelections,
    pastedImageSelections,
    pdfPanelRef,
    pdfContainerRef,
    pdfScrollRef,
    clearPendingPdfSelection,
    clearChatContext,
    confirmSelection,
    getSelectionAttachments,
    handleChatPaste,
    handleMouseUp,
    handlePageClick,
    resetScroll,
    setNumPages,
    setPdfSelections,
    setFigureSelections,
    setPendingFigureSelection,
    setPastedImageSelections,
    setScrollTop: (scrollTop: number) => {
      pdfScrollTopRef.current = scrollTop
    },
  }
}
