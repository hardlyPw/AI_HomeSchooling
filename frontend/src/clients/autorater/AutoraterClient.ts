import { AUTORATER_API_URL } from '../../constants'
import { httpClient } from '../httpClient'

export interface StartAutoraterResponse {
  opener: string
  total_problems: number
  mode?: string
}

export interface AutoraterChatResponse {
  reply: string
  next_opener?: string
  mode?: string
  next_mode?: string
  is_done: boolean
}

export class AutoraterClient {
  getExamples(): Promise<{ images: string[] }> {
    return httpClient.getJson(`${AUTORATER_API_URL}/examples`)
  }

  preloadFirst(): Promise<{ status: string }> {
    return httpClient.postJson(`${AUTORATER_API_URL}/preload-first`)
  }

  start(imageB64: string): Promise<StartAutoraterResponse> {
    return httpClient.postJson(`${AUTORATER_API_URL}/start`, { image_b64: imageB64 })
  }

  chat(message: string): Promise<AutoraterChatResponse> {
    return httpClient.postJson(`${AUTORATER_API_URL}/chat`, { message })
  }
}

export const autoraterClient = new AutoraterClient()
