import { useCallback, useEffect, useRef, useState } from 'react'
import { gameClient, type AgentCardTurn, type MemoryMatchState } from '../../clients/games/GameClient'
import type { AgentProfile } from '../../domain/agents/AgentProfile'

const wait = (duration: number) => new Promise(resolve => window.setTimeout(resolve, duration))
const ROOM_READY_SECONDS = 10
const ACCEPTED_MODAL_MS = 1800

type ChallengeDecision = 'accepted' | 'rejected' | null

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
  const [challengePending, setChallengePending] = useState(false)
  const [challengeDecision, setChallengeDecision] = useState<ChallengeDecision>(null)
  const [isRoomCountdown, setIsRoomCountdown] = useState(false)
  const [error, setError] = useState('')
  const [quickMenuOpen, setQuickMenuOpen] = useState(false)
  const [userBubble, setUserBubble] = useState('')
  const [agentBubble, setAgentBubble] = useState('')
  const boardValues = useRef<number[]>([])
  const selectedCardsRef = useRef<number[]>([])
  const actionInFlight = useRef(false)
  const userBubbleTimer = useRef<number | null>(null)
  const agentReplyTimer = useRef<number | null>(null)
  const agentBubbleTimer = useRef<number | null>(null)
  const challengeRequestId = useRef(0)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 200)
    return () => {
      challengeRequestId.current += 1
      window.clearInterval(timer)
      if (userBubbleTimer.current !== null) window.clearTimeout(userBubbleTimer.current)
      if (agentReplyTimer.current !== null) window.clearTimeout(agentReplyTimer.current)
      if (agentBubbleTimer.current !== null) window.clearTimeout(agentBubbleTimer.current)
    }
  }, [])

  const showAgentBubble = useCallback((text: string) => {
    if (agentBubbleTimer.current !== null) window.clearTimeout(agentBubbleTimer.current)
    setAgentBubble(text)
    agentBubbleTimer.current = window.setTimeout(() => {
      setAgentBubble('')
      agentBubbleTimer.current = null
    }, 3000)
  }, [])

  const start = async () => {
    const selectedAgent = agents.find(agent => agent.id === selectedAgentId)
    if (!selectedAgent) return
    const requestId = challengeRequestId.current + 1
    challengeRequestId.current = requestId
    setIsBusy(true)
    setChallengePending(true)
    setChallengeDecision(null)
    setError('')
    try {
      const challengeDelay = 3000 + Math.floor(Math.random() * 2001)
      if (!selectedAgent.isOnline) {
        await wait(challengeDelay)
        if (requestId !== challengeRequestId.current) return
        setChallengePending(false)
        setChallengeDecision('rejected')
        return
      }
      const [next] = await Promise.all([gameClient.startMemoryMatch(selectedAgentId), wait(challengeDelay)])
      if (requestId !== challengeRequestId.current) return
      setChallengePending(false)
      setChallengeDecision('accepted')
      await wait(ACCEPTED_MODAL_MS)
      if (requestId !== challengeRequestId.current) return
      boardValues.current = next.cards.map(card => card.value ?? 0)
      setState(next)
      setChallengeDecision(null)
      setIsRoomCountdown(true)
      setDisplayAgentScore(0)
      setSelectedCards([])
      selectedCardsRef.current = []
      const startedAt = Date.now()
      setNow(startedAt)
      setPhaseStartedAt(startedAt)
    } catch (requestError) {
      setChallengeDecision(null)
      setError(requestError instanceof Error ? requestError.message : 'Could not start Memory Match.')
    } finally {
      if (requestId === challengeRequestId.current) {
        setChallengePending(false)
        setIsBusy(false)
      }
    }
  }

  const dismissRejectedChallenge = () => {
    if (challengeDecision !== 'rejected') return
    setChallengeDecision(null)
  }

  const roomRemaining = state?.phase === 'preview' && isRoomCountdown
    ? Math.max(0, ROOM_READY_SECONDS - Math.floor((now - phaseStartedAt) / 1000))
    : 0
  const previewRemaining = state?.phase === 'preview' && !isRoomCountdown
    ? Math.max(0, state.preview_seconds - Math.floor((now - phaseStartedAt) / 1000))
    : 0
  const turnRemaining = state?.phase === 'player_turn'
    ? Math.max(0, state.turn_seconds - Math.floor((now - phaseStartedAt) / 1000))
    : 0

  useEffect(() => {
    if (!state || state.phase !== 'preview' || !isRoomCountdown || roomRemaining > 0) return
    const transitionTimer = window.setTimeout(() => {
      const startedAt = Date.now()
      setIsRoomCountdown(false)
      setNow(startedAt)
      setPhaseStartedAt(startedAt)
    }, 0)
    return () => window.clearTimeout(transitionTimer)
  }, [isRoomCountdown, roomRemaining, state])

  useEffect(() => {
    if (!state || state.phase !== 'preview' || isRoomCountdown || previewRemaining > 0 || actionInFlight.current) return
    actionInFlight.current = true
    gameClient.readyMemoryMatch(state.id)
      .then(next => {
        setState(next)
        setPhaseStartedAt(Date.now())
      })
      .catch(requestError => setError(requestError instanceof Error ? requestError.message : 'Could not hide the cards.'))
      .finally(() => { actionInFlight.current = false })
  }, [isRoomCountdown, previewRemaining, state])

  const animateAgentTurns = useCallback(async (turns: AgentCardTurn[]) => {
    for (const turn of turns) {
      setAgentReveal({ [turn.indices[0]]: turn.values[0], [turn.indices[1]]: turn.values[1] })
      showAgentBubble(turn.matched ? 'Found one!' : 'Your turn!')
      await wait(750)
      if (turn.matched) {
        setTemporaryMatches(current => [...current, ...turn.indices])
        setDisplayAgentScore(turn.score_after)
        await wait(350)
      }
      setAgentReveal({})
      if (!turn.matched) await wait(250)
    }
  }, [showAgentBubble])

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
    const isMatch = boardValues.current[nextSelection[0]] === boardValues.current[nextSelection[1]]
    await wait(550)
    if (!isMatch) {
      setSelectedCards([])
      selectedCardsRef.current = []
      await wait(420)
    }
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
    if (userBubbleTimer.current !== null) window.clearTimeout(userBubbleTimer.current)
    if (agentReplyTimer.current !== null) window.clearTimeout(agentReplyTimer.current)
    if (agentBubbleTimer.current !== null) window.clearTimeout(agentBubbleTimer.current)
    userBubbleTimer.current = window.setTimeout(() => {
      setUserBubble('')
      userBubbleTimer.current = null
    }, 3000)
    agentReplyTimer.current = window.setTimeout(() => {
      const replies: Record<string, string> = {
        'Good luck!': 'You too!',
        'Nice one!': 'Thanks!',
        'Watch this!': 'Show me!',
        'So close!': 'That was close!',
        'Good game!': 'Good game!',
      }
      showAgentBubble(replies[text] ?? "Let's go!")
      agentReplyTimer.current = null
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
    challengePending,
    challengeDecision,
    error,
    isRoomCountdown,
    roomRemaining,
    previewRemaining,
    showFlipWarning: state?.phase === 'preview' && !isRoomCountdown && previewRemaining > 0 && previewRemaining <= 5,
    turnRemaining,
    displayAgentScore,
    quickMenuOpen,
    setQuickMenuOpen,
    userBubble,
    agentBubble,
    start,
    dismissRejectedChallenge,
    chooseCard,
    sendQuickChat,
    cardValue: (index: number) => boardValues.current[index] ?? null,
    isRevealed: (index: number) => (state?.phase === 'preview' && !isRoomCountdown && previewRemaining > 0) || revealedIndices.has(index) || matchedIndices.has(index),
    isMatched: (index: number) => matchedIndices.has(index),
    restart: () => setState(null),
  }
}
