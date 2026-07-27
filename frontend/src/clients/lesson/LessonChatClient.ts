import { BACKEND_BASE_URL } from '../../constants'
import { sseClient, type SseMessageHandler } from '../sseClient'

export interface LessonChatRequest {
  message: string
  pdf_context?: string
  figure_context?: string
  figure_images?: string[]
  current_video_time?: number
}

export class LessonChatClient {
  streamMessage(body: LessonChatRequest, onMessage: SseMessageHandler): Promise<void> {
    return sseClient.postJsonStream(`${BACKEND_BASE_URL}/api/v1/chat/stream`, body, onMessage)
  }
}

export const lessonChatClient = new LessonChatClient()
