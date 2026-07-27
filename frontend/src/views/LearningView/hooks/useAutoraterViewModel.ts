import { useEffect, useState } from 'react'
import { AUTORATER_API_URL } from '../../../constants'
import type { Message } from '../../../types'
import {
  fetchExampleImagePaths,
  formatIsabellaText,
  loadImageAsDataUrl,
  preloadFirstAutoraterExample,
} from '../../../utils'

interface UseAutoraterViewModelParams {
  clearChatContext: () => void
  openWorkspace: () => void
  returnHome: () => void
}

export const useAutoraterViewModel = ({
  clearChatContext,
  openWorkspace,
  returnHome,
}: UseAutoraterViewModelParams) => {
  const [autoraterMode, setAutoraterMode] = useState(false)
  const [autoraterStarted, setAutoraterStarted] = useState(false)
  const [autoraterLoading, setAutoraterLoading] = useState(false)
  const [exampleInput, setExampleInput] = useState('')
  const [exampleMessages, setExampleMessages] = useState<Message[]>([])
  const [exampleImagePaths, setExampleImagePaths] = useState<string[]>([])
  const [currentExampleIndex, setCurrentExampleIndex] = useState(0)
  const [currentExampleImage, setCurrentExampleImage] = useState('')
  const [exampleImageError, setExampleImageError] = useState('')

  useEffect(() => {
    preloadFirstAutoraterExample().catch(error => {
      console.error('Error preloading first autorater example:', error)
    })
  }, [])

  useEffect(() => {
    let cancelled = false

    fetchExampleImagePaths()
      .then(images => {
        if (cancelled) return
        setExampleImagePaths(images)
        setCurrentExampleImage(prev => prev || images[0] || '')
        setExampleImageError(images.length > 0 ? '' : 'No example images were found.')
      })
      .catch(error => {
        if (!cancelled) {
          console.error('Failed to load example images:', error)
          setExampleImageError('Failed to load example images.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const resetExamplePage = () => {
    setExampleInput('')
    setExampleMessages([])
    clearChatContext()
  }

  const startAutoraterSession = async (imageB64: string, loadingText = 'Analyzing example...') => {
    setAutoraterLoading(true)
    const msgId = Date.now()
    setExampleMessages(prev => [...prev, { role: 'assistant', text: loadingText, id: msgId }])

    try {
      const response = await fetch(`${AUTORATER_API_URL}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_b64: imageB64 }),
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => response.statusText)
        throw new Error(`HTTP ${response.status}: ${detail}`)
      }
      const data = await response.json()
      setExampleMessages(prev => prev.map(m => (
        m.id === msgId ? { ...m, text: formatIsabellaText(data.opener, data.mode) } : m
      )))
      setAutoraterStarted(true)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error starting autorater:', msg)
      setExampleMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, text: `Failed to start: ${msg}` } : m
      ))
    } finally {
      setAutoraterLoading(false)
    }
  }

  const startExampleSession = async (exampleIndex: number, resetConversation: boolean) => {
    let imagePaths = exampleImagePaths

    setAutoraterMode(true)
    setAutoraterStarted(false)
    setExampleImageError('')
    openWorkspace()
    if (resetConversation) {
      resetExamplePage()
    }

    if (imagePaths.length === 0) {
      setAutoraterLoading(true)
      try {
        imagePaths = await fetchExampleImagePaths()
        setExampleImagePaths(imagePaths)
        setExampleImageError(imagePaths.length > 0 ? '' : 'No example images were found.')
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        console.error('Error loading examples:', msg)
        setExampleImageError(`Failed to load examples: ${msg}`)
        setExampleMessages(prev => [...prev, { role: 'assistant', text: `Failed to load examples: ${msg}` }])
        setAutoraterLoading(false)
        return
      }
      setAutoraterLoading(false)
    }

    const imagePath = imagePaths[exampleIndex]
    if (!imagePath) {
      setExampleImageError('No example image was found for this step.')
      setExampleMessages(prev => [...prev, { role: 'assistant', text: 'No example images were found.' }])
      return
    }

    setCurrentExampleIndex(exampleIndex)
    setCurrentExampleImage(imagePath)
    setExampleImageError('')

    try {
      const imageB64 = await loadImageAsDataUrl(imagePath)
      await startAutoraterSession(imageB64, `Loading Example ${exampleIndex + 1}...`)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error loading example:', msg)
      setExampleImageError(`Failed to prepare example: ${msg}`)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Failed to load example: ${msg}` }])
      setAutoraterLoading(false)
    }
  }

  const sendAutoraterMessage = async () => {
    const messageText = exampleInput.trim()
    if (!messageText || autoraterLoading) return

    setExampleMessages(prev => [...prev, { role: 'user', text: messageText }])
    setExampleInput('')
    setAutoraterLoading(true)

    try {
      const response = await fetch(`${AUTORATER_API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      setExampleMessages(prev => [...prev, { role: 'assistant', text: formatIsabellaText(data.reply, data.mode) }])
      if (data.next_opener) {
        setExampleMessages(prev => [...prev, {
          role: 'assistant',
          text: formatIsabellaText(data.next_opener, data.next_mode),
        }])
      }
      if (data.is_done) {
        const nextExampleIndex = currentExampleIndex + 1
        if (nextExampleIndex < exampleImagePaths.length) {
          await startExampleSession(nextExampleIndex, false)
        } else {
          setAutoraterStarted(false)
          setExampleMessages(prev => [...prev, { role: 'assistant', text: 'Isabella: Great work. You finished all of the examples.' }])
          window.setTimeout(() => {
            endExampleSession()
          }, 1200)
        }
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      console.error('Error in autorater chat:', msg)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Error: ${msg}` }])
    } finally {
      setAutoraterLoading(false)
    }
  }

  const endExampleSession = () => {
    setAutoraterMode(false)
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    resetExamplePage()
    setCurrentExampleIndex(0)
    setCurrentExampleImage(exampleImagePaths[0] || '')
    returnHome()
  }

  const resetRuntime = () => {
    setAutoraterMode(false)
    setAutoraterStarted(false)
    setAutoraterLoading(false)
  }

  return {
    autoraterMode,
    autoraterStarted,
    autoraterLoading,
    exampleInput,
    exampleMessages,
    currentExampleIndex,
    currentExampleImage,
    exampleImageError,
    endExampleSession,
    resetRuntime,
    sendAutoraterMessage,
    setExampleImageError,
    setExampleInput,
    startExampleSession,
  }
}
