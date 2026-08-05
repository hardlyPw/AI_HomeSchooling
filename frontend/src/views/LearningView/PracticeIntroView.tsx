import { ArrowLeft, BookOpen, BrainCircuit, Play, RefreshCw } from 'lucide-react'
import type { Lecture } from '../../types'

interface PracticeIntroViewProps {
  lecture: Lecture
  totalExamples: number
  isLoading: boolean
  error: string
  onStart: () => void
  onRetry: () => void
  onReturnLesson: () => void
  onReturnHome: () => void
}

export default function PracticeIntroView({
  lecture,
  totalExamples,
  isLoading,
  error,
  onStart,
  onRetry,
  onReturnLesson,
  onReturnHome,
}: PracticeIntroViewProps) {
  return (
    <main className="practice-flow-view">
      <header className="practice-flow-header">
        <button className="practice-icon-button" onClick={onReturnHome} aria-label="Back to home">
          <ArrowLeft size={20} />
        </button>
        <div>
          <span>Practice session</span>
          <strong>{lecture.title}</strong>
        </div>
      </header>

      <section className="practice-intro-content">
        <div className="practice-intro-mark" aria-hidden="true">
          <BrainCircuit size={34} />
        </div>
        <p className="practice-eyebrow">Practice with Isabella</p>
        <h1>Ready to work through the examples?</h1>
        <p className="practice-intro-copy">
          Isabella will guide you one step at a time. You decide when to move to the next example.
        </p>

        <div className="practice-session-facts">
          <div>
            <BookOpen size={20} />
            <span>
              <small>Lesson</small>
              <strong>{lecture.title}</strong>
            </span>
          </div>
          <div>
            <BrainCircuit size={20} />
            <span>
              <small>Examples</small>
              <strong>{isLoading ? 'Loading...' : `${totalExamples} available`}</strong>
            </span>
          </div>
        </div>

        {error && (
          <div className="practice-load-error" role="alert">
            <span>{error}</span>
            <button onClick={onRetry} disabled={isLoading}>
              <RefreshCw size={16} />
              Retry
            </button>
          </div>
        )}

        <div className="practice-intro-actions">
          <button className="practice-primary-action" onClick={onStart} disabled={isLoading || totalExamples === 0}>
            <Play size={18} fill="currentColor" />
            Start practice
          </button>
          <button className="practice-secondary-action" onClick={onReturnLesson}>
            Return to lesson
          </button>
        </div>
      </section>
    </main>
  )
}
