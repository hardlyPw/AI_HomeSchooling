export interface Message {
  role: 'user' | 'assistant'
  text: string
  id?: number
  attachments?: ChatAttachment[]
}

export interface ChatAttachment {
  type: 'passage' | 'figure'
  text: string
  imageUrl?: string
}

export interface PastedImageSelection {
  image: string
  name: string
}

export interface Figure {
  id: string
  page: number
  bbox: { x: number; y: number; x2: number; y2: number }
  label: string
  description: string
}

export interface FigureSelection {
  figure: Figure
  image: string | null
}

export interface SelectionButtonAnchor {
  left: number
  top: number
}

export interface Lecture {
  id: string
  title: string
  description: string
  src: string
  duration: string
}

export type LessonState = 'idle' | 'playing' | 'paused' | 'question'
export type AppMode = 'home' | 'agent-create' | 'agent-chat' | 'lesson' | 'playlist'
