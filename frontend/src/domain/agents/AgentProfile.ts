export type AgentCapability = 'free-chat' | 'affinity' | 'debug-telemetry' | 'problem-solving'
export type GameSkillTier = 'easy' | 'normal' | 'hard'

export interface AgentProfile {
  id: string
  name: string
  description: string
  entryLabel: string
  initialAffinity: number
  gameSkillTier: GameSkillTier
  isOnline: boolean
  chatEndpoint: string
  historyEndpoint?: string
  stateEndpoint?: string
  resetEndpoint?: string
  debugEndpoints?: {
    cooldown: string
    doubleText: string
    cooldownEnd: string
  }
  capabilities: AgentCapability[]
  isBuiltin?: boolean
  avatarByMood?: Record<string, string>
}
