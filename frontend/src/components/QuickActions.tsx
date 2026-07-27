import { FileText, MessageCircle } from 'lucide-react'

interface QuickActionsProps {
  showPdf: boolean
  showChat: boolean
  onToggleTextbook: () => void
  onToggleChat: () => void
}

export default function QuickActions({
  showPdf,
  showChat,
  onToggleTextbook,
  onToggleChat,
}: QuickActionsProps) {
  return (
    <div className="quick-actions" aria-label="Study tools">
      <button
        className={`quick-action ${showPdf ? 'active' : ''}`}
        onClick={onToggleTextbook}
        aria-label={showPdf ? 'Hide textbook' : 'Show textbook'}
        title={showPdf ? 'Hide textbook' : 'Show textbook'}
      >
        <FileText size={22} />
      </button>
      <button
        className={`quick-action ${showChat ? 'active' : ''}`}
        onClick={onToggleChat}
        aria-label={showChat ? 'Hide chat' : 'Show chat'}
        title={showChat ? 'Hide chat' : 'Show chat'}
      >
        <MessageCircle size={22} />
      </button>
    </div>
  )
}
