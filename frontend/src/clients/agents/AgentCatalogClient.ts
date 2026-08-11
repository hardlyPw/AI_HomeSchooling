import { BACKEND_BASE_URL } from '../../constants'
import type { AgentCapability, AgentProfile, GameSkillTier } from '../../domain/agents/AgentProfile'
import { httpClient } from '../httpClient'

export interface AgentSummaryResponse {
  id: string
  type: string
  name: string
  description: string
  initial_affinity: number
  game_skill_tier: GameSkillTier
  capabilities: string[]
  is_builtin: boolean
}

interface AgentListResponse {
  agents: AgentSummaryResponse[]
}

export interface CreateAgentRequest {
  requested_name: string
  relationship: string
  personality: string
  speech_style: string
  interests: string
  reaction_style: string
  background: string
  avoidances: string
  dialogue_examples: string
  additional_description: string
}

const mapCapabilities = (values: string[]): AgentCapability[] => {
  const capabilities: AgentCapability[] = ['free-chat']
  if (values.includes('affinity')) capabilities.push('affinity')
  if (values.includes('debug_controls')) capabilities.push('debug-telemetry')
  return capabilities
}

const toProfile = (agent: AgentSummaryResponse): AgentProfile => {
  const root = `${BACKEND_BASE_URL}/api/v1/agents/${agent.id}`
  return {
    id: agent.id,
    name: agent.name,
    description: agent.description,
    entryLabel: `Talk with ${agent.name}`,
    initialAffinity: agent.initial_affinity,
    gameSkillTier: agent.game_skill_tier,
    chatEndpoint: `${root}/chat/stream`,
    historyEndpoint: `${root}/history`,
    stateEndpoint: `${root}/state`,
    resetEndpoint: `${root}/reset`,
    debugEndpoints: agent.capabilities.includes('debug_controls')
      ? {
          cooldown: `${root}/debug/cooldown`,
          doubleText: `${root}/debug/double-text`,
          cooldownEnd: `${root}/debug/cooldown-end`,
        }
      : undefined,
    capabilities: mapCapabilities(agent.capabilities),
    isBuiltin: agent.is_builtin,
  }
}

export class AgentCatalogClient {
  async listAgents(): Promise<AgentProfile[]> {
    const response = await httpClient.getJson<AgentListResponse>(
      `${BACKEND_BASE_URL}/api/v1/agents`,
    )
    return response.agents.map(toProfile)
  }

  async createAgent(request: CreateAgentRequest): Promise<AgentProfile> {
    const response = await httpClient.postJson<AgentSummaryResponse, CreateAgentRequest>(
      `${BACKEND_BASE_URL}/api/v1/agents`,
      request,
    )
    return toProfile(response)
  }

  deleteAgent(agentId: string): Promise<void> {
    return httpClient.delete(`${BACKEND_BASE_URL}/api/v1/agents/${agentId}`)
  }
}

export const agentCatalogClient = new AgentCatalogClient()
