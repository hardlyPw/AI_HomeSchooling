import type { ClipboardEvent, KeyboardEvent, RefObject } from 'react'
import { X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import type { FigureSelection, Message, PastedImageSelection } from '../types'
import { getAttachmentPreview, normalizeMathMarkdown } from '../utils'

interface StudyChatPanelProps {
  autoraterMode: boolean
  autoraterStarted: boolean
  autoraterLoading: boolean
  activeInput: string
  activeMessages: Message[]
  pdfSelections: string[]
  figureSelections: FigureSelection[]
  pastedImageSelections: PastedImageSelection[]
  currentExampleIndex: number
  currentExampleImage: string
  exampleImageError: string
  scrollRef: RefObject<HTMLDivElement | null>
  chatInputRef: RefObject<HTMLInputElement | null>
  onClose: () => void
  onEndExampleSession: () => void
  onExampleImageLoad: () => void
  onExampleImageError: () => void
  onInputChange: (value: string) => void
  onInputPaste: (event: ClipboardEvent<HTMLInputElement>) => void
  onInputEnter: (event: KeyboardEvent<HTMLInputElement>) => void
  onSend: () => void
  onRemovePdfSelection: (index: number) => void
  onRemoveFigureSelection: (index: number) => void
  onRemovePastedImageSelection: (index: number) => void
}

export default function StudyChatPanel({
  autoraterMode,
  autoraterStarted,
  autoraterLoading,
  activeInput,
  activeMessages,
  pdfSelections,
  figureSelections,
  pastedImageSelections,
  currentExampleIndex,
  currentExampleImage,
  exampleImageError,
  scrollRef,
  chatInputRef,
  onClose,
  onEndExampleSession,
  onExampleImageLoad,
  onExampleImageError,
  onInputChange,
  onInputPaste,
  onInputEnter,
  onSend,
  onRemovePdfSelection,
  onRemoveFigureSelection,
  onRemovePastedImageSelection,
}: StudyChatPanelProps) {
  const hasContext = pdfSelections.length > 0 || figureSelections.length > 0 || pastedImageSelections.length > 0

  return (
    <div className={autoraterMode ? 'split-panel autorater-chat-panel' : 'floating-panel chat-panel'}>
      <div className="panel-header">
        <span>{autoraterMode ? 'Solving Examples with Isabella' : 'Chat'}</span>
        {autoraterMode ? (
          <button className="panel-action" onClick={onEndExampleSession}>
            End example session
          </button>
        ) : (
          <button className="panel-close" onClick={onClose} aria-label="Close chat">
            <X size={18} />
          </button>
        )}
      </div>

      <div className="chat-view">
        {autoraterMode && (
          <div className="autorater-example-preview">
            <div className="autorater-example-title">Example {currentExampleIndex + 1}</div>
            {currentExampleImage ? (
              <img
                src={currentExampleImage}
                alt={`Example ${currentExampleIndex + 1}`}
                onLoad={onExampleImageLoad}
                onError={onExampleImageError}
              />
            ) : (
              <div className="autorater-example-placeholder">
                Loading example image...
              </div>
            )}
            {exampleImageError && (
              <div className="autorater-example-error">
                {exampleImageError}
              </div>
            )}
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

        {!autoraterMode && hasContext && (
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
                  onClick={() => onRemovePdfSelection(i)}
                  aria-label="Remove passage"
                >
                  x
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
                  onClick={() => onRemoveFigureSelection(i)}
                  aria-label="Remove figure"
                >
                  x
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
                  onClick={() => onRemovePastedImageSelection(i)}
                  aria-label="Remove pasted image"
                >
                  x
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="input-area">
          <input
            ref={chatInputRef}
            value={activeInput}
            onChange={e => onInputChange(e.target.value)}
            onPaste={onInputPaste}
            onKeyDown={onInputEnter}
            placeholder={
              autoraterMode && !autoraterStarted
                ? 'Isabella is getting ready...'
                : autoraterMode
                ? 'Reply to Isabella...'
                : 'Type a message...'
            }
            disabled={autoraterLoading || (autoraterMode && !autoraterStarted)}
          />
          <button
            onClick={onSend}
            disabled={autoraterLoading || (autoraterMode && !autoraterStarted)}
          >
            {autoraterLoading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
