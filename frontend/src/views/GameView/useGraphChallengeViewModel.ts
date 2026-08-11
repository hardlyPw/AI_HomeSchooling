import { compile } from 'mathjs'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { gameClient, type GraphChallengeState, type GraphPoint } from '../../clients/games/GameClient'

const ROUND_SECONDS = 60

const expressionPoints = (expression: string): GraphPoint[] => {
  try {
    const evaluator = compile(expression || '0')
    const points: GraphPoint[] = []
    for (let index = 0; index <= 120; index += 1) {
      const x = -6 + index * 0.1
      const raw = Number(evaluator.evaluate({ x }))
      if (Number.isFinite(raw) && raw >= -36 && raw <= 36) {
        points.push({ x, y: Math.max(-12, Math.min(12, raw)) })
      }
    }
    return points
  } catch {
    return []
  }
}

export const useGraphChallengeViewModel = () => {
  const [state, setState] = useState<GraphChallengeState | null>(null)
  const [expression, setExpression] = useState('x')
  const [roundStartedAt, setRoundStartedAt] = useState(0)
  const [now, setNow] = useState(0)
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState('')
  const expressionRef = useRef(expression)
  const submittedRoundRef = useRef('')

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(timer)
  }, [])

  const start = async () => {
    setIsBusy(true)
    setError('')
    try {
      const next = await gameClient.startGraphChallenge()
      setState(next)
      setExpression('x')
      expressionRef.current = 'x'
      submittedRoundRef.current = ''
      const startedAt = Date.now()
      setNow(startedAt)
      setRoundStartedAt(startedAt)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not start Graph Challenge.')
    } finally {
      setIsBusy(false)
    }
  }

  const submit = useCallback(async () => {
    if (!state || state.current_round.completed || isBusy) return
    const roundKey = `${state.id}:${state.current_round.number}`
    if (submittedRoundRef.current === roundKey) return
    if (expressionPoints(expressionRef.current).length < 2) {
      setError('Enter a valid function of x before submitting.')
      return
    }
    submittedRoundRef.current = roundKey
    setIsBusy(true)
    setError('')
    try {
      const next = await gameClient.submitGraphExpression(
        state.id,
        expressionRef.current,
        Math.min(ROUND_SECONDS * 1000, Date.now() - roundStartedAt),
      )
      setState(next)
    } catch (requestError) {
      submittedRoundRef.current = ''
      setError(requestError instanceof Error ? requestError.message : 'Could not score this graph.')
    } finally {
      setIsBusy(false)
    }
  }, [isBusy, roundStartedAt, state])

  useEffect(() => {
    if (!state || state.current_round.completed || roundStartedAt === 0) return
    const delay = Math.max(0, roundStartedAt + ROUND_SECONDS * 1000 - Date.now())
    const timeout = window.setTimeout(() => void submit(), delay)
    return () => window.clearTimeout(timeout)
  }, [roundStartedAt, state, submit])

  const advance = async () => {
    if (!state || isBusy) return
    setIsBusy(true)
    setError('')
    try {
      const next = await gameClient.advanceGraphChallenge(state.id)
      setState(next)
      setExpression('x')
      expressionRef.current = 'x'
      submittedRoundRef.current = ''
      const startedAt = Date.now()
      setNow(startedAt)
      setRoundStartedAt(startedAt)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not open the next round.')
    } finally {
      setIsBusy(false)
    }
  }

  const remainingSeconds = roundStartedAt
    ? Math.max(0, ROUND_SECONDS - Math.floor((now - roundStartedAt) / 1000))
    : ROUND_SECONDS

  return {
    state,
    expression,
    playerPoints: useMemo(() => expressionPoints(expression), [expression]),
    remainingSeconds,
    isBusy,
    error,
    start,
    submit,
    advance,
    setExpression: (value: string) => {
      expressionRef.current = value
      setExpression(value)
    },
    restart: () => setState(null),
  }
}
