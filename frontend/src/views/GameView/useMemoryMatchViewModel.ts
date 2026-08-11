import { useCallback, useEffect, useRef, useState } from 'react'
import { gameClient, type AgentCardTurn, type MemoryMatchState } from '../../clients/games/GameClient'
import type { AgentProfile } from '../../domain/agents/AgentProfile'

const wait = (duration: number) => new Promise(resolve => window.setTimeout(resolve, duration))

export const useMemoryMatchViewModel = (agents: AgentProfile[]) => {
  const [selectedAgentId, setSelectedAgentId] = useState(agents[0]?.id ?? 'jiho')
  const [state, setState] = useState<MemoryMatchState | null>(null)
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const [agentReveal, setAgentReveal] = useState<Record<number, number>>({})
  const [temporaryMatches, setTemporaryMatches] = useState<number[]>([])
  const [displayAgentScore, setDisplayAgentScore] = useState(0)
  const [phaseStartedAt, setPhaseStartedAt] = useState(0)
  const [now, setNow] = useState(0)
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState('')
  const [quickMenuOpen, setQuickMenuOpen] = useState(false)
  const [userBubble, setUserBubble] = useState('')
  const [agentBubble, setAgentBubble] = useState('')
  const boardValues = useRef<number[]>([])
  const selectedCardsRef = useRef<number[]>([])
  const actionInFlight = useRef(false)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 200)
    return () => window.clearInterval(timer)
  }, [])

  const start = async () => {
    setIsBusy(true)
    setError('')
    try {
      const next = await gameClient.startMemoryMatch(selectedAgentId)
      boardValues.current = next.cards.map(card => card.value ?? 0)
      setState(next)
      setDisplayAgentScore(0)
      setSelectedCards([])
      selectedCardsRef.current = []
      const startedAt = Date.now()
      setNow(startedAt)
      setPhaseStartedAt(startedAt)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not start Memory Match.')
    } finally {
      setIsBusy(false)
    }
  }

  const previewRemaining = state?.phase === 'preview'
    ? Math.max(0, state.preview_seconds - Math.floor((now - phaseStartedAt) / 1000))
    : 0
  const turnRemaining = state?.phase === 'player_turn'
    ? Math.max(0, state.turn_seconds - Math.floor((now - phaseStartedAt) / 1000))
    : 0

  useEffect(() => {
    if (!state || state.phase !== 'preview' || previewRemaining > 0 || actionInFlight.current) return
    actionInFlight.current = true
    gameClient.readyMemoryMatch(state.id)
      .then(next => {
        setState(next)
        setPhaseStartedAt(Date.now())
      })
      .catch(requestError => setError(requestError instanceof Error ? requestError.message : 'Could not hide the cards.'))
      .finally(() => { actionInFlight.current = false })
  }, [previewRemaining, state])

  const animateAgentTurns = useCallback(async (turns: AgentCardTurn[]) => {
    for (const turn of turns) {
      setAgentReveal({ [turn.indices[0]]: turn.values[0], [turn.indices[1]]: turn.values[1] })
      setAgentBubble(turn.matched ? 'Found one!' : 'Your turn!')
      await wait(750)
      if (turn.matched) {
        setTemporaryMatches(current => [...current, ...turn.indices])
        setDisplayAgentScore(turn.score_after)
        await wait(350)
      }
      setAgentReveal({})
      if (!turn.matched) await wait(250)
    }
  }, [])

  const applyServerTurn = useCallback(async (request: Promise<MemoryMatchState>) => {
    setIsBusy(true)
    setError('')
    actionInFlight.current = true
    try {
      const next = await request
      await animateAgentTurns(next.agent_turns)
      setState(next)
      setDisplayAgentScore(next.agent_score)
      setSelectedCards([])
      selectedCardsRef.current = []
      setAgentReveal({})
      setTemporaryMatches([])
      setPhaseStartedAt(Date.now())
    } catch (requestError) {
      setSelectedCards([])
      selectedCardsRef.current = []
      setError(requestError instanceof Error ? requestError.message : 'The turn could not be completed.')
    } finally {
      actionInFlight.current = false
      setIsBusy(false)
    }
  }, [animateAgentTurns])

  const chooseCard = async (index: number) => {
    if (!state || state.phase !== 'player_turn' || isBusy || selectedCardsRef.current.includes(index) || state.cards[index]?.matched) return
    const nextSelection = [...selectedCardsRef.current, index]
    selectedCardsRef.current = nextSelection
    setSelectedCards(nextSelection)
    if (nextSelection.length < 2) return
    actionInFlight.current = true
    setIsBusy(true)
    await wait(550)
    await applyServerTurn(gameClient.playMemoryCards(state.id, [nextSelection[0], nextSelection[1]]))
  }

  const passTurn = useCallback(async () => {
    if (!state || state.phase !== 'player_turn' || actionInFlight.current) return
    await applyServerTurn(gameClient.passMemoryTurn(state.id))
  }, [applyServerTurn, state])

  useEffect(() => {
    if (!state || state.phase !== 'player_turn' || turnRemaining > 0 || actionInFlight.current) return
    void passTurn()
  }, [passTurn, state, turnRemaining])

  const sendQuickChat = (text: string) => {
    setQuickMenuOpen(false)
    setUserBubble(text)
    setAgentBubble('')
    window.setTimeout(() => {
      const replies: Record<string, string> = {
        'Good luck!': 'You too!',
        'Nice one!': 'Thanks!',
        'Watch this!': 'Show me!',
        'So close!': 'That was close!',
        'Good game!': 'Good game!',
      }
      setAgentBubble(replies[text] ?? 'Let’s go!')
    }, 900)
  }

  const revealedIndices = new Set([...selectedCards, ...Object.keys(agentReveal).map(Number)])
  const matchedIndices = new Set([
    ...(state?.cards.filter(card => card.matched).map(card => card.index) ?? []),
    ...temporaryMatches,
  ])

  return {
    agents,
    selectedAgentId,
    setSelectedAgentId,
    selectedAgent: agents.find(agent => agent.id === (state?.agent_id ?? selectedAgentId)) ?? agents[0],
    state,
    isBusy,
    error,
    previewRemaining,
    turnRemaining,
    displayAgentScore,
    quickMenuOpen,
    setQuickMenuOpen,
    userBubble,
    agentBubble,
    start,
    chooseCard,
    sendQuickChat,
    cardValue: (index: number) => boardValues.current[index] ?? null,
    isRevealed: (index: number) => state?.phase === 'preview' || revealedIndices.has(index) || matchedIndices.has(index),
    isMatched: (index: number) => matchedIndices.has(index),
    restart: () => setState(null),
  }
}
