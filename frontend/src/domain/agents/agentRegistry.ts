import { BACKEND_BASE_URL } from '../../constants'
import type { AgentProfile } from './AgentProfile'

export const agentRegistry: Record<string, AgentProfile> = {
  jiho: {
    id: 'jiho',
    name: 'Jiho',
    description: 'A blunt peer friend with affinity, memory, and debug telemetry.',
    entryLabel: 'Talk with Jiho',
    initialAffinity: 70,
    chatEndpoint: `${BACKEND_BASE_URL}/api/v1/agents/jiho/chat/stream`,
    historyEndpoint: `${BACKEND_BASE_URL}/api/v1/agents/jiho/history`,
    stateEndpoint: `${BACKEND_BASE_URL}/api/v1/agents/jiho/state`,
    resetEndpoint: `${BACKEND_BASE_URL}/api/v1/agents/jiho/reset`,
    debugEndpoints: {
      cooldown: `${BACKEND_BASE_URL}/api/v1/agents/jiho/debug/cooldown`,
      doubleText: `${BACKEND_BASE_URL}/api/v1/agents/jiho/debug/double-text`,
      cooldownEnd: `${BACKEND_BASE_URL}/api/v1/agents/jiho/debug/cooldown-end`,
    },
    capabilities: ['free-chat', 'affinity', 'debug-telemetry'],
    avatarByMood: {
      joy: '/assets/jiho/jiho_joy.png',
      happy: '/assets/jiho/jiho_happy.png',
      neutral: '/assets/jiho/jiho_neutral.png',
      annoyed: '/assets/jiho/jiho_annoyed.png',
      sulk: '/assets/jiho/jiho_sulk.png',
    },
  },
}

export const getAgentProfile = (agentId: string) => agentRegistry[agentId] ?? agentRegistry.jiho

export const listAgentProfiles = () => Object.values(agentRegistry)

export const upsertAgentProfiles = (profiles: AgentProfile[]) => {
  profiles.forEach(profile => {
    const existing = agentRegistry[profile.id]
    agentRegistry[profile.id] = {
      ...existing,
      ...profile,
      avatarByMood: profile.avatarByMood ?? existing?.avatarByMood,
    }
  })
}
