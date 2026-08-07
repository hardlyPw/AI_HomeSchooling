import { useEffect, useState } from 'react'
import {
  autoraterClient,
  type PracticeSet,
} from '../../../clients/autorater/AutoraterClient'
import type { Message } from '../../../types'
import { formatIsabellaText, loadImageAsDataUrl } from '../../../utils'

export type PracticePhase = 'idle' | 'intro' | 'solving' | 'example-complete' | 'summary'
const PRACTICE_SET: PracticeSet = 'focused'

interface UseAutoraterViewModelParams {
  clearChatContext: () => void
  openWorkspace: () => void
  closeWorkspace: () => void
}

export const useAutoraterViewModel = ({
  clearChatContext,
  openWorkspace,
  closeWorkspace,
}: UseAutoraterViewModelParams) => {
  const [autoraterMode, setAutoraterMode] = useState(false)
  const [practicePhase, setPracticePhase] = useState<PracticePhase>('idle')
  const [autoraterStarted, setAutoraterStarted] = useState(false)
  const [autoraterLoading, setAutoraterLoading] = useState(false)
  const [exampleInput, setExampleInput] = useState('')
  const [exampleMessages, setExampleMessages] = useState<Message[]>([])
  const [exampleImagePaths, setExampleImagePaths] = useState<string[]>([])
  const [currentExampleIndex, setCurrentExampleIndex] = useState(0)
  const [currentExampleImage, setCurrentExampleImage] = useState('')
  const [currentProblemTotal, setCurrentProblemTotal] = useState(0)
  const [exampleImageError, setExampleImageError] = useState('')
  const [practiceError, setPracticeError] = useState('')
  const [completedExamples, setCompletedExamples] = useState(0)
  const [userMessageCount, setUserMessageCount] = useState(0)
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const totalExamples = exampleImagePaths.length
  const isLastExample = totalExamples > 0 && currentExampleIndex === totalExamples - 1

  useEffect(() => {
    autoraterClient.preloadFirst(PRACTICE_SET).catch(error => {
      console.error('Error preloading first autorater example:', error)
    })
  }, [])

  const loadExamples = async () => {
    setAutoraterLoading(true)
    setExampleImageError('')
    try {
      const { images } = await autoraterClient.getExamples(PRACTICE_SET)
      setExampleImagePaths(images)
      setCurrentExampleImage(images[0] || '')
      if (images.length === 0) {
        setExampleImageError('No example images were found.')
      }
      return images
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.error('Failed to load example images:', error)
      setExampleImageError(`Failed to load examples: ${message}`)
      return []
    } finally {
      setAutoraterLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    autoraterClient.getExamples(PRACTICE_SET)
      .then(({ images }) => {
        if (cancelled) return
        setExampleImagePaths(images)
        setCurrentExampleImage(images[0] || '')
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

  const preparePractice = () => {
    closeWorkspace()
    resetExamplePage()
    setAutoraterMode(true)
    setPracticePhase('intro')
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    setCurrentExampleIndex(0)
    setCurrentExampleImage(exampleImagePaths[0] || '')
    setCurrentProblemTotal(0)
    setPracticeError('')
    setCompletedExamples(0)
    setUserMessageCount(0)
    setSessionStartedAt(null)
    setElapsedSeconds(0)
  }

  const startAutoraterSession = async (imageB64: string, loadingText: string) => {
    setAutoraterLoading(true)
    setAutoraterStarted(false)
    setPracticeError('')
    const messageId = Date.now()
    setExampleMessages(prev => [...prev, { role: 'assistant', text: loadingText, id: messageId }])

    try {
      const data = await autoraterClient.start(imageB64)
      setExampleMessages(prev => prev.map(message => (
        message.id === messageId
          ? { ...message, text: formatIsabellaText(data.opener, data.mode) }
          : message
      )))
      setCurrentProblemTotal(data.total_problems)
      setAutoraterStarted(true)
      setPracticePhase('solving')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.error('Error starting autorater:', message)
      setExampleMessages(prev => prev.map(item => (
        item.id === messageId ? { ...item, text: `Failed to start: ${message}` } : item
      )))
      setPracticeError(`Isabella could not start this example: ${message}`)
    } finally {
      setAutoraterLoading(false)
    }
  }

  const startExampleSession = async (exampleIndex: number, resetConversation: boolean) => {
    let imagePaths = exampleImagePaths
    openWorkspace()
    setPracticePhase('solving')
    setAutoraterStarted(false)
    setExampleImageError('')
    setPracticeError('')
    if (resetConversation) resetExamplePage()

    if (imagePaths.length === 0) {
      imagePaths = await loadExamples()
    }

    const imagePath = imagePaths[exampleIndex]
    if (!imagePath) {
      setExampleImageError('No example image was found for this step.')
      return
    }

    setCurrentExampleIndex(exampleIndex)
    setCurrentExampleImage(imagePath)
    setCurrentProblemTotal(0)

    try {
      const imageB64 = await loadImageAsDataUrl(imagePath)
      await startAutoraterSession(imageB64, `Loading Example ${exampleIndex + 1}...`)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.error('Error loading example:', message)
      setExampleImageError(`Failed to prepare example: ${message}`)
      setAutoraterLoading(false)
    }
  }

  const beginPractice = async () => {
    setCompletedExamples(0)
    setUserMessageCount(0)
    setElapsedSeconds(0)
    setSessionStartedAt(Date.now())
    await startExampleSession(0, true)
  }

  const sendAutoraterMessage = async () => {
    const messageText = exampleInput.trim()
    if (!messageText || autoraterLoading || practicePhase !== 'solving') return

    setExampleMessages(prev => [...prev, { role: 'user', text: messageText }])
    setExampleInput('')
    setUserMessageCount(prev => prev + 1)
    setAutoraterLoading(true)

    try {
      const data = await autoraterClient.chat(messageText)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: formatIsabellaText(data.reply, data.mode) }])
      if (data.next_opener) {
        setExampleMessages(prev => [...prev, {
          role: 'assistant',
          text: formatIsabellaText(data.next_opener!, data.next_mode),
        }])
      }
      if (data.is_done) {
        setCompletedExamples(prev => Math.max(prev, currentExampleIndex + 1))
        setAutoraterStarted(false)
        setPracticePhase('example-complete')
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.error('Error in autorater chat:', message)
      setExampleMessages(prev => [...prev, { role: 'assistant', text: `Error: ${message}` }])
    } finally {
      setAutoraterLoading(false)
    }
  }

  const continuePractice = async () => {
    if (practicePhase !== 'example-complete') return
    if (isLastExample) {
      const seconds = sessionStartedAt ? Math.max(1, Math.round((Date.now() - sessionStartedAt) / 1000)) : 0
      setElapsedSeconds(seconds)
      setPracticePhase('summary')
      closeWorkspace()
      return
    }
    await startExampleSession(currentExampleIndex + 1, false)
  }

  const retryCurrentExample = async () => {
    setPracticeError('')
    setExampleMessages(prev => prev.filter(message => !message.text.startsWith('Failed to start:')))
    await startExampleSession(currentExampleIndex, false)
  }

  const resetRuntime = () => {
    closeWorkspace()
    setAutoraterMode(false)
    setPracticePhase('idle')
    setAutoraterStarted(false)
    setAutoraterLoading(false)
    setExampleInput('')
    setExampleMessages([])
    setCurrentExampleIndex(0)
    setCurrentExampleImage(exampleImagePaths[0] || '')
    setCurrentProblemTotal(0)
    setExampleImageError('')
    setPracticeError('')
    setCompletedExamples(0)
    setUserMessageCount(0)
    setSessionStartedAt(null)
    setElapsedSeconds(0)
    clearChatContext()
  }

  return {
    autoraterMode,
    practicePhase,
    autoraterStarted,
    autoraterLoading,
    exampleInput,
    exampleMessages,
    currentExampleIndex,
    currentExampleImage,
    currentProblemTotal,
    exampleImageError,
    practiceError,
    completedExamples,
    userMessageCount,
    elapsedSeconds,
    totalExamples,
    isLastExample,
    beginPractice,
    continuePractice,
    loadExamples,
    preparePractice,
    resetRuntime,
    retryCurrentExample,
    sendAutoraterMessage,
    setExampleImageError,
    setExampleInput,
  }
}
