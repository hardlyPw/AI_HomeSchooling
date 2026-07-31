export type SseMessageHandler = (event: Record<string, unknown>) => void

export class SseClient {
  async postJsonStream<TBody>(url: string, body: TBody, onMessage: SseMessageHandler): Promise<void> {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)

    await this.consume(response.body, onMessage)
  }

  async consume(stream: ReadableStream<Uint8Array>, onMessage: SseMessageHandler): Promise<void> {
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let sepIdx
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx)
          buffer = buffer.slice(sepIdx + 2)

          for (const line of rawEvent.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try {
              const parsed = JSON.parse(line.slice(6))
              if (parsed && typeof parsed === 'object') {
                onMessage(parsed as Record<string, unknown>)
              }
            } catch {
              // Ignore malformed or heartbeat events.
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }
}

export const sseClient = new SseClient()
