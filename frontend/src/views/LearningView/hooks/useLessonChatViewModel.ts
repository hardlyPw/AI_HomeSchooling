import { useRef, useState, type KeyboardEvent } from 'react'
import { lessonChatClient, type LessonChatRequest } from '../../../clients/lesson/LessonChatClient'
import type { Message } from '../../../types'

interface SendLessonMessageParams {
  pdfSelections: string[]
  figureSelections: { figure: { label: string; description: string }; image: string | null }[]
  pastedImageSelections: { image: string }[]
  attachments: Message['attachments']
  currentVideoTime?: number
  clearContext: () => void
  ensureChatOpen: () => void
}

export const useLessonChatViewModel = () => {
  const [lessonInput, setLessonInput] = useState('')
  const [lessonMessages, setLessonMessages] = useState<Message[]>([])
  const messageIdRef = useRef(0)

  const reset = () => {
    setLessonInput('')
    setLessonMessages([])
  }

  const sendLessonMessage = async ({
    pdfSelections,
    figureSelections,
    pastedImageSelections,
    attachments,
    currentVideoTime,
    clearContext,
    ensureChatOpen,
  }: SendLessonMessageParams) => {
    const hasContext = pdfSelections.length > 0 || figureSelections.length > 0 || pastedImageSelections.length > 0
    const messageText = lessonInput.trim() || (hasContext ? 'Explain this.' : '')
    if (!messageText) return

    ensureChatOpen()
    setLessonMessages(prev => [...prev, { role: 'user', text: messageText, attachments }])
    setLessonInput('')

    const body: LessonChatRequest = { message: messageText }

    if (pdfSelections.length > 0) {
      body.pdf_context = pdfSelections
        .map((s, i) => `Passage ${i + 1}:\n"""\n${s}\n"""`)
        .join('\n\n')
    }

    const figureImages = [
      ...figureSelections
        .map(s => s.image)
        .filter((img): img is string => !!img),
      ...pastedImageSelections.map(s => s.image),
    ]

    if (figureSelections.length > 0) {
      body.figure_context = figureSelections
        .map((s, i) => {
          const desc = s.figure.description ? s.figure.description : '(no description)'
          return `Figure ${i + 1} - Label: ${s.figure.label}. Description: ${desc}`
        })
        .join('\n\n')
    }
    if (figureImages.length > 0) body.figure_images = figureImages
    if (currentVideoTime && currentVideoTime > 0) {
      body.current_video_time = currentVideoTime
    }

    clearContext()

    const msgId = ++messageIdRef.current
    setLessonMessages(prev => [...prev, { role: 'assistant', text: '', id: msgId }])

    try {
      await lessonChatClient.streamMessage(body, obj => {
        if (typeof obj.delta === 'string') {
          setLessonMessages(prev => prev.map(m =>
            m.id === msgId ? { ...m, text: m.text + obj.delta } : m
          ))
        } else if (obj.error) {
          setLessonMessages(prev => prev.map(m =>
            m.id === msgId ? { ...m, text: `Error: ${obj.error}` } : m
          ))
        }
      })
    } catch (error) {
      console.error('Error:', error)
      setLessonMessages(prev => prev.map(m => (
        m.id === msgId ? { ...m, text: 'Failed to reach the assistant.' } : m
      )))
    }
  }

  const handleEnter = (e: KeyboardEvent<HTMLInputElement>, onSend: () => void) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    onSend()
  }

  return {
    lessonInput,
    lessonMessages,
    reset,
    sendLessonMessage,
    setLessonInput,
    handleEnter,
  }
}
