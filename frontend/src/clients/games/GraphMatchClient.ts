import { BACKEND_BASE_URL } from '../../constants'
import type { GameSkillTier } from '../../domain/agents/AgentProfile'
import { httpClient } from '../httpClient'

export interface GraphPoint {
  x: number
  y: number
}

export interface GraphFunctionInput {
  coefficient: -1 | 1
  base: number
  horizontal_shift: number
  vertical_shift: number
}

export type QuickChatId = 'hello' | 'nice' | 'try_harder' | 'great_play' | 'close' | 'good_game'

export interface GraphAttempt {
  latex: string
  score: number
  elapsed_ms: number
}

export interface GraphMatchState {
  id: string
  agent_id: string
  agent_name: string
  agent_skill: GameSkillTier
  round_count: number
  current_round: {
    number: number
    target_points: GraphPoint[]
    attempts: GraphAttempt[]
    attempts_remaining: number
    completed: boolean
    target_latex: string | null
    agent_latex: string | null
    agent_points: GraphPoint[]
    agent_score: number | null
    winner: 'user' | 'agent' | 'draw' | null
  }
  user_round_wins: number
  agent_round_wins: number
  completed: boolean
  overall_winner: 'user' | 'agent' | 'draw' | null
  quick_chats: Array<{ sender: 'user' | 'agent'; chat: QuickChatId; text: string }>
}

const headers = { 'X-User-ID': 'demo-user' }
const root = `${BACKEND_BASE_URL}/api/v1/games/graph-match/sessions`

export class GraphMatchClient {
  start(agentId: string): Promise<GraphMatchState> {
    return httpClient.postJson(root, { agent_id: agentId }, headers)
  }

  submitAttempt(
    sessionId: string,
    input: GraphFunctionInput & { elapsed_ms: number },
  ): Promise<GraphMatchState> {
    return httpClient.postJson(`${root}/${sessionId}/attempts`, input, headers)
  }

  advance(sessionId: string): Promise<GraphMatchState> {
    return httpClient.postJson(`${root}/${sessionId}/advance`, undefined, headers)
  }

  sendQuickChat(sessionId: string, chat: QuickChatId): Promise<GraphMatchState> {
    return httpClient.postJson(`${root}/${sessionId}/quick-chats`, { chat }, headers)
  }
}

export const graphMatchClient = new GraphMatchClient()
