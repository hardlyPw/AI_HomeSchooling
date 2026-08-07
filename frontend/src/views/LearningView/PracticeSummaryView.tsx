import { BookOpen, Check, Clock3, Home, MessageCircle, RotateCcw } from 'lucide-react'
import type { Lecture } from '../../types'

interface PracticeSummaryViewProps {
  lecture: Lecture
  completedExamples: number
  totalExamples: number
  userMessageCount: number
  elapsedSeconds: number
  onRestart: () => void
  onReturnLesson: () => void
  onReturnHome: () => void
}

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes === 0) return `${remainingSeconds}s`
  return `${minutes}m ${remainingSeconds}s`
}

export default function PracticeSummaryView({
  lecture,
  completedExamples,
  totalExamples,
  userMessageCount,
  elapsedSeconds,
  onRestart,
  onReturnLesson,
  onReturnHome,
}: PracticeSummaryViewProps) {
  return (
    <main className="practice-flow-view practice-summary-view">
      <section className="practice-summary-content">
        <div className="practice-summary-check" aria-hidden="true">
          <Check size={34} strokeWidth={3} />
        </div>
        <p className="practice-eyebrow">Session complete</p>
        <h1>Nice work.</h1>
        <p className="practice-intro-copy">You completed the practice set for {lecture.title}.</p>

        <div className="practice-summary-stats">
          <div>
            <BookOpen size={20} />
            <strong>{completedExamples} / {totalExamples}</strong>
            <span>Practice sets completed</span>
          </div>
          <div>
            <MessageCircle size={20} />
            <strong>{userMessageCount}</strong>
            <span>Replies sent</span>
          </div>
          <div>
            <Clock3 size={20} />
            <strong>{formatDuration(elapsedSeconds)}</strong>
            <span>Practice time</span>
          </div>
        </div>

        <div className="practice-summary-actions">
          <button className="practice-primary-action" onClick={onReturnLesson}>
            <BookOpen size={18} />
            Return to lesson
          </button>
          <button className="practice-secondary-action" onClick={onRestart}>
            <RotateCcw size={18} />
            Practice again
          </button>
          <button className="practice-text-action" onClick={onReturnHome}>
            <Home size={17} />
            Home
          </button>
        </div>
      </section>
    </main>
  )
}
