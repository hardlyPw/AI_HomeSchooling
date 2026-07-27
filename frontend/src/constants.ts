import type { Lecture } from './types'

export const BACKEND_BASE_URL = 'http://localhost:8000'
export const AUTORATER_API_URL = `${BACKEND_BASE_URL}/api/v1/autorater`

export const LECTURES: Lecture[] = [
  {
    id: 'chapter-4-1',
    title: 'Ch. 4.1 Exponential Functions',
    description: 'Learn the definition and core behavior of exponential functions.',
    src: '/assets/video.mp4',
    duration: '20:36',
  },
]
