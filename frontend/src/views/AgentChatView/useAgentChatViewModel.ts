import { useEffect, useRef, useState } from 'react'
import { agentChatClient } from '../../clients/agents/AgentChatClient'
import { getAgentProfile } from '../../domain/agents/agentRegistry'

export type AgentExpression = 'joy' | 'happy' | 'neutral' | 'annoyed' | 'sulk'

export interface AgentChatMessage {
  role: 'user' | 'assistant'
  text: string
  id: number
  timestamp: string
}

interface AgentHistoryMessage {
  role: 'user' | 'ai' | 'assistant'
  text: string
}

interface AgentHistoryResponse {
  affinity: number
  messages: AgentHistoryMessage[]
}

interface AgentResetResponse {
  affinity: number
}

export interface AgentDecisionLogEntry {
  id: number
  turn: number
  timestamp: string
  user_message: string
  emotion: string
  emotion_reason: string
  timing: string
  action: string
  affinity_prev: number
  affinity_next: number
  affinity_delta: number
  affinity_reason: string
  reasoning: string
  away_mode: string
  response_seconds: number | null
  decision_prompt_tokens: number | null
  decision_completion_tokens: number | null
  reply_prompt_tokens: number | null
  reply_completion_tokens: number | null
  total_tokens: number | null
}

function nowHHMM(): string {
  return new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function affinityToExpression(affinity: number): AgentExpression {
  if (affinity >= 85) return 'joy'
  if (affinity >= 60) return 'happy'
  if (affinity >= 35) return 'neutral'
  if (affinity >= 15) return 'annoyed'
  return 'sulk'
}

function toDecisionLog(
  decision: Record<string, unknown>,
  id: number,
  turn: number,
): AgentDecisionLogEntry {
  return {
    id,
    turn,
    timestamp: nowHHMM(),
    user_message: String(decision.user_message ?? ''),
    emotion: String(decision.emotion ?? ''),
    emotion_reason: String(decision.emotion_reason ?? ''),
    timing: String(decision.timing ?? ''),
    action: String(decision.action ?? ''),
    affinity_prev: Number(decision.affinity_prev ?? 0),
    affinity_next: Number(decision.affinity_next ?? 0),
    affinity_delta: Number(decision.affinity_delta ?? 0),
    affinity_reason: String(decision.affinity_reason ?? ''),
    reasoning: String(decision.reasoning ?? ''),
    away_mode: String(decision.away_mode ?? ''),
    response_seconds: null,
    decision_prompt_tokens: null,
    decision_completion_tokens: null,
    reply_prompt_tokens: null,
    reply_completion_tokens: null,
    total_tokens: null,
  }
}

export function useAgentChatViewModel(agentId: string) {
  const agent = getAgentProfile(agentId)
  const [messages, setMessages] = useState<AgentChatMessage[]>([])
  const [input, setInput] = useState('')
  const [affinity, setAffinity] = useState(agent.initialAffinity)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [showDebug, setShowDebug] = useState(false)
  const [cooldownArmed, setCooldownArmed] = useState(false)
  const [doubleTextArmed, setDoubleTextArmed] = useState(false)
  const [isOnline, setIsOnline] = useState(true)
  const [decisionLog, setDecisionLog] = useState<AgentDecisionLogEntry[]>([])
  const idRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false

    agentChatClient
      .getHistory<AgentHistoryResponse>(agentId)
      .then(data => {
        if (cancelled) return
        if (typeof data.affinity === 'number') setAffinity(data.affinity)
        if (!Array.isArray(data.messages)) return

        const restored = data.messages
          .filter(message => (
            message.role === 'user'
            || message.role === 'ai'
            || message.role === 'assistant'
          ))
          .map((message, index): AgentChatMessage => ({
            role: message.role === 'user' ? 'user' : 'assistant',
            text: message.text,
            id: index + 1,
            timestamp: nowHHMM(),
          }))
        idRef.current = restored.length
        setMessages(restored)
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [agent.initialAffinity, agentId])

  useEffect(() => {
    inputRef.current?.focus()
  }, [agentId])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isTyping])

  const reset = async () => {
    if (isStreaming) return
    setMessages([])
    setCooldownArmed(false)
    setDoubleTextArmed(false)
    setIsOnline(true)
    setDecisionLog([])
    try {
      const data = await agentChatClient.reset<AgentResetResponse>(agentId)
      if (typeof data.affinity === 'number') setAffinity(data.affinity)
    } catch {
      setAffinity(agent.initialAffinity)
    }
  }

  const forceCooldown = async () => {
    if (isStreaming) return
    try {
      await agentChatClient.forceCooldown(agentId)
      setCooldownArmed(true)
    } catch {
      // Debug controls should not interrupt the conversation UI.
    }
  }

  const forceDoubleText = async () => {
    if (isStreaming) return
    try {
      await agentChatClient.forceDoubleText(agentId)
      setDoubleTextArmed(true)
    } catch {
      // Debug controls should not interrupt the conversation UI.
    }
  }

  const endCooldown = async () => {
    try {
      await agentChatClient.endCooldown(agentId)
    } catch {
      // Debug controls should not interrupt the conversation UI.
    }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setCooldownArmed(false)
    setDoubleTextArmed(false)
    setIsStreaming(true)
    setIsTyping(true)
    setMessages(previous => [...previous, {
      role: 'user',
      text,
      id: ++idRef.current,
      timestamp: nowHHMM(),
    }])

    let activeAssistantId = ++idRef.current
    let assistantStarted = false

    try {
      await agentChatClient.streamMessage(agentId, text, event => {
        if (event.message_break === true) {
          activeAssistantId = ++idRef.current
          assistantStarted = true
          setIsTyping(false)
          setMessages(previous => [...previous, {
            role: 'assistant',
            text: '',
            id: activeAssistantId,
            timestamp: nowHHMM(),
          }])
        } else if (typeof event.delta === 'string') {
          setIsOnline(true)
          const targetAssistantId = activeAssistantId
          if (!assistantStarted) {
            assistantStarted = true
            setIsTyping(false)
            setMessages(previous => [...previous, {
              role: 'assistant',
              text: '',
              id: targetAssistantId,
              timestamp: nowHHMM(),
            }])
          }
          setMessages(previous => previous.map(message => (
            message.id === targetAssistantId
              ? { ...message, text: message.text + event.delta }
              : message
          )))
        } else if (typeof event.affinity === 'number') {
          setAffinity(event.affinity)
        } else if (event.decision && typeof event.decision === 'object') {
          const decision = event.decision as Record<string, unknown>
          setDecisionLog(previous => [
            ...previous,
            toDecisionLog(decision, ++idRef.current, previous.length + 1),
          ])
        } else if (event.timing && typeof event.timing === 'object') {
          const timing = event.timing as Record<string, unknown>
          if (typeof timing.total_seconds !== 'number') return
          setDecisionLog(previous => {
            if (previous.length === 0) return previous
            const next = previous.slice()
            next[next.length - 1] = {
              ...next[next.length - 1],
              response_seconds: timing.total_seconds as number,
            }
            return next
          })
        } else if (event.tokens && typeof event.tokens === 'object') {
          const tokens = event.tokens as Record<string, unknown>
          setDecisionLog(previous => {
            if (previous.length === 0) return previous
            const next = previous.slice()
            next[next.length - 1] = {
              ...next[next.length - 1],
              decision_prompt_tokens: typeof tokens.decision_prompt === 'number' ? tokens.decision_prompt : null,
              decision_completion_tokens: typeof tokens.decision_completion === 'number' ? tokens.decision_completion : null,
              reply_prompt_tokens: typeof tokens.reply_prompt === 'number' ? tokens.reply_prompt : null,
              reply_completion_tokens: typeof tokens.reply_completion === 'number' ? tokens.reply_completion : null,
              total_tokens: typeof tokens.total === 'number' ? tokens.total : null,
            }
            return next
          })
        } else if (event.status === 'cooldown') {
          setIsOnline(false)
          setIsTyping(false)
        } else if (event.status === 'delayed') {
          setIsTyping(true)
        } else if (event.error) {
          setMessages(previous => [...previous, {
            role: 'assistant',
            text: `Warning: ${String(event.error)}`,
            id: ++idRef.current,
            timestamp: nowHHMM(),
          }])
        }
      })
    } catch (error) {
      console.error(error)
      setMessages(previous => [...previous, {
        role: 'assistant',
        text: 'Connection failed.',
        id: ++idRef.current,
        timestamp: nowHHMM(),
      }])
    } finally {
      setIsStreaming(false)
      setIsTyping(false)
      setIsOnline(true)
    }
  }

  return {
    agent,
    affinity,
    canDebug: agent.capabilities.includes('debug-telemetry'),
    clearDecisionLog: () => setDecisionLog([]),
    cooldownArmed,
    decisionLog,
    doubleTextArmed,
    endCooldown,
    expression: affinityToExpression(affinity),
    forceCooldown,
    forceDoubleText,
    hasAvatar: Boolean(agent.avatarByMood),
    input,
    bindInput: (element: HTMLInputElement | null) => {
      inputRef.current = element
    },
    isOnline,
    isStreaming,
    isTyping,
    messages,
    reset,
    bindScrollContainer: (element: HTMLDivElement | null) => {
      scrollRef.current = element
    },
    send,
    setInput,
    showDebug,
    toggleDebug: () => setShowDebug(value => !value),
  }
}

export type AgentChatViewModel = ReturnType<typeof useAgentChatViewModel>
