import { AUTORATER_API_URL } from './constants'
import type { PastedImageSelection } from './types'

const LATEX_COMMAND_PATTERN = String.raw`\\(?:frac|sqrt|left|right|cdot|times|div|sum|int|text|log|ln|sin|cos|tan|theta|pi|alpha|beta|gamma|Delta|le|ge|neq|approx|infty|lim)`

export const normalizeMathMarkdown = (markdown: string) => {
  const protectedLatexParens = markdown
    .replace(/\\left\(/g, String.raw`\left\lparen`)
    .replace(/\\right\)/g, String.raw`\right\rparen`)
    .replace(/\\left\[/g, String.raw`\left\lbrack`)
    .replace(/\\right\]/g, String.raw`\right\rbrack`)

  return protectedLatexParens
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_, expr: string) => `\n\n$$\n${expr.trim()}\n$$\n\n`)
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_, expr: string) => `$${expr.trim()}$`)
    .replace(
      new RegExp(String.raw`\((\s*(?=[^\n]*${LATEX_COMMAND_PATTERN}|[^\n]*[A-Za-z]\s*[_^])[^\n]*?)\)(?=[,.;:]?\s|$)`, 'g'),
      (match: string, expr: string) => {
        const trimmed = expr.trim()
        return trimmed && !trimmed.includes('$') ? `$${trimmed}$` : match
      },
    )
    .replace(/\(\s*([abmnrtxy])\s*\)/g, '$$$1$$')
}

export const fetchExampleImagePaths = async () => {
  const response = await fetch(`${AUTORATER_API_URL}/examples`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const data: { images?: unknown } = await response.json()
  return Array.isArray(data.images)
    ? data.images.filter((image): image is string => typeof image === 'string')
    : []
}

export const preloadFirstAutoraterExample = async () => {
  const response = await fetch(`${AUTORATER_API_URL}/preload-first`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
}

export const getAttachmentPreview = (text: string, maxLength = 180) => {
  const normalized = text.replace(/\s+/g, ' ').trim()
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
}

export const readImageFileAsDataUrl = (file: File) => new Promise<PastedImageSelection>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve({
    image: String(reader.result),
    name: file.name || 'Pasted image',
  })
  reader.onerror = () => reject(reader.error)
  reader.readAsDataURL(file)
})

export const loadImageAsDataUrl = async (src: string) => {
  const response = await fetch(src)
  if (!response.ok) throw new Error(`Failed to load ${src}`)
  const blob = await response.blob()
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export const formatIsabellaText = (text: string, mode?: string) => {
  const hasModeLabel = /^\s*\[mode:/i.test(text)
  const modePrefix = mode && !hasModeLabel ? `[mode: ${mode}] ` : ''
  return `Isabella: ${modePrefix}${text}`
}

export const captureVideoThumbnail = (src: string) => new Promise<string>((resolve, reject) => {
  const video = document.createElement('video')
  video.src = src
  video.muted = true
  video.preload = 'metadata'
  video.playsInline = true

  const cleanup = () => {
    video.removeAttribute('src')
    video.load()
  }

  video.onloadedmetadata = () => {
    video.currentTime = Math.min(3, Math.max(0, (video.duration || 6) * 0.12))
  }
  video.onseeked = () => {
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || 640
    canvas.height = video.videoHeight || 360
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      cleanup()
      reject(new Error('Could not capture video thumbnail'))
      return
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.82)
    cleanup()
    resolve(dataUrl)
  }
  video.onerror = () => {
    cleanup()
    reject(new Error(`Could not load ${src}`))
  }
})
