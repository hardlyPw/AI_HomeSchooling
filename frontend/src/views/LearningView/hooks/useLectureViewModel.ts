import { useEffect, useRef, useState } from 'react'
import { LECTURES } from '../../../constants'
import type { LessonState } from '../../../types'
import { captureVideoThumbnail } from '../../../utils'

export const useLectureViewModel = () => {
  const [lessonState, setLessonState] = useState<LessonState>('idle')
  const [selectedLectureId, setSelectedLectureId] = useState(LECTURES[0].id)
  const [lectureThumbnails, setLectureThumbnails] = useState<Record<string, string>>({})
  const videoRef = useRef<HTMLVideoElement | null>(null)

  const selectedLecture = LECTURES.find(lecture => lecture.id === selectedLectureId) ?? LECTURES[0]

  useEffect(() => {
    let cancelled = false
    LECTURES.forEach(lecture => {
      captureVideoThumbnail(lecture.src)
        .then(thumbnail => {
          if (!cancelled) {
            setLectureThumbnails(prev => ({ ...prev, [lecture.id]: thumbnail }))
          }
        })
        .catch(console.error)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const handleVideoShortcuts = (e: globalThis.KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, [contenteditable="true"]')) return
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return

      const video = videoRef.current
      if (!video) return

      e.preventDefault()
      const delta = e.key === 'ArrowRight' ? 5 : -5
      const duration = Number.isFinite(video.duration) ? video.duration : Number.POSITIVE_INFINITY
      video.currentTime = Math.min(Math.max(video.currentTime + delta, 0), duration)
    }

    window.addEventListener('keydown', handleVideoShortcuts)
    return () => window.removeEventListener('keydown', handleVideoShortcuts)
  }, [])

  return {
    lessonState,
    selectedLecture,
    selectedLectureId,
    lectureThumbnails,
    videoRef,
    setLessonState,
    setSelectedLectureId,
    pause: () => videoRef.current?.pause(),
  }
}
