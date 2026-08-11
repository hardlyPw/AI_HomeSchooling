import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  graphMatchClient,
  type GraphFunctionInput,
  type GraphMatchState,
  type GraphPoint,
  type QuickChatId,
} from '../../clients/games/GraphMatchClient'
import type { AgentProfile } from '../../domain/agents/AgentProfile'

const ROUND_SECONDS = 60

const functionPoints = (input: GraphFunctionInput): GraphPoint[] =>
  Array.from({ length: 81 }, (_, index) => {
    const x = -4 + index * 0.1
    const value = input.coefficient * input.base ** (x - input.horizontal_shift) + input.vertical_shift
    return { x, y: Math.max(-8, Math.min(12, value)) }
  })

export const formulaLatex = (input: GraphFunctionInput) => {
  const base = input.base === 1 / 3 ? '\\frac{1}{3}' : input.base === 1 / 2 ? '\\frac{1}{2}' : String(input.base)
  const exponent = input.horizontal_shift > 0
    ? `x-${input.horizontal_shift}`
    : input.horizontal_shift < 0
      ? `x+${Math.abs(input.horizontal_shift)}`
      : 'x'
  const vertical = input.vertical_shift > 0 ? `+${input.vertical_shift}` : input.vertical_shift || ''
  return `f(x)=${input.coefficient < 0 ? '-' : ''}\\left(${base}\\right)^{${exponent}}${vertical}`
}

export interface GraphMatchViewModel {
  agents: AgentProfile[]
  selectedAgentId: string
  setSelectedAgentId: (value: string) => void
  state: GraphMatchState | null
  input: GraphFunctionInput
  updateInput: (values: Partial<GraphFunctionInput>) => void
  playerPoints: GraphPoint[]
  formula: string
  remainingSeconds: number
  isBusy: boolean
  error: string
  start: () => Promise<void>
  submit: () => Promise<void>
  advance: () => Promise<void>
  quickChat: (chat: QuickChatId) => Promise<void>
  restart: () => void
}

export const useGraphMatchViewModel = (agents: AgentProfile[]): GraphMatchViewModel => {
  const [selectedAgentId, setSelectedAgentId] = useState('jiho')
  const [state, setState] = useState<GraphMatchState | null>(null)
  const [input, setInput] = useState<GraphFunctionInput>({ coefficient: 1, base: 2, horizontal_shift: 0, vertical_shift: 0 })
  const [now, setNow] = useState(0)
  const [roundStartedAt, setRoundStartedAt] = useState(0)
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(input)
  const submittedRoundRef = useRef('')
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(timer)
  }, [])

  const run = useCallback(async (request: () => Promise<GraphMatchState>) => {
    setIsBusy(true)
    setError('')
    try {
      const next = await request()
      setState(next)
      return next
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The game service is unavailable.')
      return null
    } finally {
      setIsBusy(false)
    }
  }, [])

  const start = async () => {
    const next = await run(() => graphMatchClient.start(selectedAgentId))
    if (next) setRoundStartedAt(Date.now())
  }

  const submit = useCallback(async () => {
    if (!state || state.current_round.completed) return
    const roundKey = `${state.id}:${state.current_round.number}`
    if (submittedRoundRef.current === roundKey) return
    submittedRoundRef.current = roundKey
    const next = await run(() => graphMatchClient.submitAttempt(state.id, {
      ...inputRef.current,
      elapsed_ms: Math.min(ROUND_SECONDS * 1000, Date.now() - roundStartedAt),
    }))
    if (!next) submittedRoundRef.current = ''
  }, [roundStartedAt, run, state])

  const advance = async () => {
    if (!state) return
    const next = await run(() => graphMatchClient.advance(state.id))
    if (next) {
      const initialInput: GraphFunctionInput = { coefficient: 1, base: 2, horizontal_shift: 0, vertical_shift: 0 }
      inputRef.current = initialInput
      setInput(initialInput)
      submittedRoundRef.current = ''
      setRoundStartedAt(Date.now())
    }
  }

  const remainingSeconds = roundStartedAt === 0
    ? ROUND_SECONDS
    : Math.max(0, ROUND_SECONDS - Math.floor((now - roundStartedAt) / 1000))

  useEffect(() => {
    if (!state || state.current_round.completed || roundStartedAt === 0) return
    const delay = Math.max(0, roundStartedAt + ROUND_SECONDS * 1000 - Date.now())
    const timeout = window.setTimeout(() => void submit(), delay)
    return () => window.clearTimeout(timeout)
  }, [roundStartedAt, state, submit])

  return {
    agents,
    selectedAgentId,
    setSelectedAgentId,
    state,
    input,
    updateInput: values => setInput(current => {
      const next = { ...current, ...values }
      inputRef.current = next
      return next
    }),
    playerPoints: useMemo(() => functionPoints(input), [input]),
    formula: useMemo(() => formulaLatex(input), [input]),
    remainingSeconds,
    isBusy,
    error,
    start,
    submit,
    advance,
    quickChat: async chat => {
      if (!state) return
      await run(() => graphMatchClient.sendQuickChat(state.id, chat))
    },
    restart: () => setState(null),
  }
}
