export type AgentCapability = 'free-chat' | 'affinity' | 'debug-telemetry' | 'problem-solving'

export interface AgentProfile {
  id: string
  name: string
  description: string
  entryLabel: string
  chatEndpoint: string
  historyEndpoint?: string
  stateEndpoint?: string
  resetEndpoint?: string
  capabilities: AgentCapability[]
  avatarByMood?: Record<string, string>
}
