export class HttpClient {
  private async throwResponseError(response: Response): Promise<never> {
    let detail = ''
    try {
      const payload = await response.json() as { detail?: unknown }
      if (typeof payload.detail === 'string') detail = payload.detail
    } catch {
      // Some endpoints return an empty or non-JSON error response.
    }
    throw new Error(detail ? `HTTP ${response.status}: ${detail}` : `HTTP ${response.status}`)
  }

  async getJson<T>(url: string, headers?: HeadersInit): Promise<T> {
    const response = await fetch(url, { headers })
    if (!response.ok) await this.throwResponseError(response)
    return response.json() as Promise<T>
  }

  async postJson<TResponse, TBody = unknown>(
    url: string,
    body?: TBody,
    headers?: HeadersInit,
  ): Promise<TResponse> {
    const requestHeaders = new Headers(headers)
    requestHeaders.set('Content-Type', 'application/json')
    const response = await fetch(url, {
      method: 'POST',
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!response.ok) await this.throwResponseError(response)
    return response.json() as Promise<TResponse>
  }

  async delete(url: string, headers?: HeadersInit): Promise<void> {
    const response = await fetch(url, { method: 'DELETE', headers })
    if (!response.ok) await this.throwResponseError(response)
  }
}

export const httpClient = new HttpClient()
