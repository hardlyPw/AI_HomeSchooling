import { getAgentProfile } from '../../domain/agents/agentRegistry'
import { httpClient } from '../httpClient'
import { sseClient, type SseMessageHandler } from '../sseClient'

export class AgentChatClient {
  getHistory<T>(agentId: string): Promise<T> {
    const agent = getAgentProfile(agentId)
    if (!agent.historyEndpoint) throw new Error(`${agent.name} does not expose history.`)
    return httpClient.getJson<T>(agent.historyEndpoint)
  }

  reset<T>(agentId: string): Promise<T> {
    const agent = getAgentProfile(agentId)
    if (!agent.resetEndpoint) throw new Error(`${agent.name} does not expose reset.`)
    return httpClient.postJson<T>(agent.resetEndpoint)
  }

  streamMessage(agentId: string, message: string, onMessage: SseMessageHandler): Promise<void> {
    const agent = getAgentProfile(agentId)
    return sseClient.postJsonStream(agent.chatEndpoint, { message }, onMessage)
  }
}

export const agentChatClient = new AgentChatClient()
