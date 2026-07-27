import type { RefObject } from 'react'
import { FastForward, ListVideo } from 'lucide-react'
import type { Lecture, LessonState } from '../types'

interface LessonStageProps {
  selectedLecture: Lecture
  lessonState: LessonState
  autoraterMode: boolean
  videoRef: RefObject<HTMLVideoElement | null>
  onLessonStateChange: (state: LessonState) => void
  onOpenPlaylist: () => void
  onEnterAutoraterMode: () => void
}

export default function LessonStage({
  selectedLecture,
  lessonState,
  autoraterMode,
  videoRef,
  onLessonStateChange,
  onOpenPlaylist,
  onEnterAutoraterMode,
}: LessonStageProps) {
  if (autoraterMode) return null

  return (
    <div className="teacher-view">
      <video
        ref={videoRef}
        src={selectedLecture.src}
        className="character-video"
        controls
        preload="metadata"
        onPlay={() => onLessonStateChange('playing')}
        onPause={() => onLessonStateChange('paused')}
        onEnded={() => onLessonStateChange('paused')}
        playsInline
      />

      {lessonState === 'question' && (
        <div className="lesson-progress">Asking question</div>
      )}

      <button className="playlist-return" onClick={onOpenPlaylist}>
        <ListVideo size={17} />
        Lecture playlist
      </button>

      <div className="lesson-buttons" aria-label="Lesson controls">
        <button
          className={`btn-question ${autoraterMode ? 'active' : ''}`}
          onClick={onEnterAutoraterMode}
          aria-label="Practice with Isabella"
          title="Practice with Isabella"
        >
          <FastForward size={20} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  )
}
