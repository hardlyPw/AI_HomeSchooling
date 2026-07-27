import { BACKEND_BASE_URL } from '../../constants'
import type { AgentProfile } from './AgentProfile'

export const agentRegistry: Record<string, AgentProfile> = {
  jiho: {
    id: 'jiho',
    name: 'Jiho',
    description: 'A blunt peer friend with affinity, memory, and debug telemetry.',
    entryLabel: 'Talk with Jiho',
    chatEndpoint: `${BACKEND_BASE_URL}/api/v1/friend/chat/stream`,
    historyEndpoint: `${BACKEND_BASE_URL}/api/v1/friend/history`,
    stateEndpoint: `${BACKEND_BASE_URL}/api/v1/friend/state`,
    resetEndpoint: `${BACKEND_BASE_URL}/api/v1/friend/reset`,
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
