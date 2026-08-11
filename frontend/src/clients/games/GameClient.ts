import { BACKEND_BASE_URL } from '../../constants'
import type { GameSkillTier } from '../../domain/agents/AgentProfile'
import { httpClient } from '../httpClient'

export interface GraphPoint {
  x: number
  y: number
}

export interface GraphChallengeAttempt {
  expression: string
  graph_score: number
  time_bonus: number
  score: number
  elapsed_ms: number
}

export interface GraphChallengeRound {
  number: number
  family: string
  target_points: GraphPoint[]
  target_latex: string | null
  attempt: GraphChallengeAttempt | null
  completed: boolean
}

export interface GraphChallengeState {
  id: string
  player_name: string
  round_count: number
  current_round: GraphChallengeRound
  rounds: GraphChallengeRound[]
  total_score: number
  completed: boolean
}

export interface MemoryCard {
  index: number
  value: number | null
  matched: boolean
}

export interface AgentCardTurn {
  indices: [number, number]
  values: [number, number]
  matched: boolean
  score_after: number
}

export interface MemoryMatchState {
  id: string
  agent_id: string
  agent_name: string
  agent_skill: GameSkillTier
  phase: 'preview' | 'player_turn' | 'agent_turn' | 'completed'
  cards: MemoryCard[]
  user_score: number
  agent_score: number
  winner: 'user' | 'agent' | 'draw' | null
  preview_seconds: number
  turn_seconds: number
  agent_turns: AgentCardTurn[]
}

export type GameId = 'graph_challenge' | 'memory_match'

export interface LeaderboardEntry {
  rank: number
  player_name: string
  score: number
  detail: string
  played_at: string
}

export interface LeaderboardState {
  game_id: GameId
  view_mode: 'ranking' | 'match_history'
  entries: LeaderboardEntry[]
}

const headers = { 'X-User-ID': 'demo-user' }
const root = `${BACKEND_BASE_URL}/api/v1/games`

export class GameClient {
  startGraphChallenge(): Promise<GraphChallengeState> {
    return httpClient.postJson(`${root}/graph-challenge/sessions`, { player_name: 'You' }, headers)
  }

  submitGraphExpression(sessionId: string, expression: string, elapsedMs: number): Promise<GraphChallengeState> {
    return httpClient.postJson(`${root}/graph-challenge/sessions/${sessionId}/attempts`, {
      expression,
      elapsed_ms: elapsedMs,
    }, headers)
  }

  advanceGraphChallenge(sessionId: string): Promise<GraphChallengeState> {
    return httpClient.postJson(`${root}/graph-challenge/sessions/${sessionId}/advance`, undefined, headers)
  }

  startMemoryMatch(agentId: string): Promise<MemoryMatchState> {
    return httpClient.postJson(`${root}/memory-match/sessions`, { agent_id: agentId, player_name: 'You' }, headers)
  }

  readyMemoryMatch(sessionId: string): Promise<MemoryMatchState> {
    return httpClient.postJson(`${root}/memory-match/sessions/${sessionId}/ready`, undefined, headers)
  }

  playMemoryCards(sessionId: string, indices: [number, number]): Promise<MemoryMatchState> {
    return httpClient.postJson(`${root}/memory-match/sessions/${sessionId}/play`, { indices }, headers)
  }

  passMemoryTurn(sessionId: string): Promise<MemoryMatchState> {
    return httpClient.postJson(`${root}/memory-match/sessions/${sessionId}/pass`, undefined, headers)
  }

  leaderboard(gameId: GameId): Promise<LeaderboardState> {
    return httpClient.getJson(`${root}/leaderboards/${gameId}`)
  }
}

export const gameClient = new GameClient()
