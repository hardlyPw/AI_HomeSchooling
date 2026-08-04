export class HttpClient {
  async getJson<T>(url: string, headers?: HeadersInit): Promise<T> {
    const response = await fetch(url, { headers })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
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
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json() as Promise<TResponse>
  }

  async delete(url: string, headers?: HeadersInit): Promise<void> {
    const response = await fetch(url, { method: 'DELETE', headers })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
  }
}

export const httpClient = new HttpClient()
