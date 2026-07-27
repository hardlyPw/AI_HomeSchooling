import type { MouseEvent, RefObject } from 'react'
import { X } from 'lucide-react'
import { Document, Page, pdfjs } from 'react-pdf'
import type { FigureSelection, SelectionButtonAnchor } from '../types'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

interface PdfPanelProps {
  autoraterMode: boolean
  showPdf: boolean
  numPages: number
  containerWidth: number
  pendingPdfSelection: string
  pendingFigureSelection: FigureSelection | null
  selectionButtonAnchor: SelectionButtonAnchor | null
  pdfPanelRef: RefObject<HTMLDivElement | null>
  pdfContainerRef: RefObject<HTMLDivElement | null>
  pdfScrollRef: RefObject<HTMLDivElement | null>
  onClose: () => void
  onConfirmSelection: () => void
  onMouseUp: () => void
  onPageClick: (event: MouseEvent<HTMLDivElement>, pageNumber: number) => void
  onScrollTopChange: (scrollTop: number) => void
  onDocumentLoad: (numPages: number) => void
}

export default function PdfPanel({
  autoraterMode,
  showPdf,
  numPages,
  containerWidth,
  pendingPdfSelection,
  pendingFigureSelection,
  selectionButtonAnchor,
  pdfPanelRef,
  pdfContainerRef,
  pdfScrollRef,
  onClose,
  onConfirmSelection,
  onMouseUp,
  onPageClick,
  onScrollTopChange,
  onDocumentLoad,
}: PdfPanelProps) {
  return (
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
          <button className="panel-close" onClick={onClose} aria-label="Close textbook">
            <X size={18} />
          </button>
        )}
      </div>

      {!autoraterMode && (pendingPdfSelection || pendingFigureSelection) && (
        <button
          className="btn-pdf-select"
          onClick={onConfirmSelection}
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

      <div className="pdf-section" ref={pdfContainerRef} onMouseUp={autoraterMode ? undefined : onMouseUp}>
        <div
          className="pdf-scroll"
          ref={pdfScrollRef}
          onScroll={e => onScrollTopChange(e.currentTarget.scrollTop)}
        >
          <Document
            file="/assets/Chapter4.pdf"
            onLoadSuccess={({ numPages }) => onDocumentLoad(numPages)}
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
                  onClick={e => onPageClick(e, pageNum)}
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
  )
}
