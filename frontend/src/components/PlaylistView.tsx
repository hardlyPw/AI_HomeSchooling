import { PlayCircle } from 'lucide-react'
import type { Lecture } from '../types'

interface PlaylistViewProps {
  lectures: Lecture[]
  selectedLectureId: string
  lectureThumbnails: Record<string, string>
  onOpenLecture: (lectureId: string) => void
}

export default function PlaylistView({
  lectures,
  selectedLectureId,
  lectureThumbnails,
  onOpenLecture,
}: PlaylistViewProps) {
  const firstLectureThumbnail = lectureThumbnails[lectures[0]?.id ?? '']

  return (
    <div className="main-layout playlist-view">
      <aside className="playlist-hero">
        <div className="playlist-card">
          {firstLectureThumbnail ? (
            <img src={firstLectureThumbnail} alt="" className="playlist-cover" />
          ) : (
            <div className="playlist-cover playlist-cover-placeholder" />
          )}
          <div className="playlist-card-body">
            <p className="playlist-kicker">Lecture Playlist</p>
            <h1>Exponential and Logarithmic Functions</h1>
            <button className="playlist-play-all" onClick={() => onOpenLecture(lectures[0].id)}>
              <PlayCircle size={18} fill="currentColor" />
              Play first lecture
            </button>
          </div>
        </div>
      </aside>

      <main className="playlist-main">
        <div className="lecture-list" aria-label="Lecture videos">
          {lectures.map((lecture, index) => (
            <button
              key={lecture.id}
              className={`lecture-row ${lecture.id === selectedLectureId ? 'active' : ''}`}
              onClick={() => onOpenLecture(lecture.id)}
            >
              <span className="lecture-index">{index + 1}</span>
              <span className="lecture-thumb-wrap">
                {lectureThumbnails[lecture.id] ? (
                  <img src={lectureThumbnails[lecture.id]} alt="" className="lecture-thumb" />
                ) : (
                  <span className="lecture-thumb lecture-thumb-placeholder" />
                )}
                <span className="lecture-duration">{lecture.duration}</span>
              </span>
              <span className="lecture-meta">
                <strong>{lecture.title}</strong>
                <span>AI HomeSchooling - {lecture.description}</span>
              </span>
            </button>
          ))}
        </div>
      </main>
    </div>
  )
}
