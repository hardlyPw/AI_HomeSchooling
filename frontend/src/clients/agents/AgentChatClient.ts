import { getAgentProfile } from '../../domain/agents/agentRegistry'
import { httpClient } from '../httpClient'
import { sseClient, type SseMessageHandler } from '../sseClient'
import { getOrCreateFriendSessionId } from './friendSession'

export class AgentChatClient {
  private get sessionHeaders(): HeadersInit {
    return { 'X-Session-ID': getOrCreateFriendSessionId() }
  }

  getHistory<T>(agentId: string): Promise<T> {
    const agent = getAgentProfile(agentId)
    if (!agent.historyEndpoint) throw new Error(`${agent.name} does not expose history.`)
    return httpClient.getJson<T>(agent.historyEndpoint, this.sessionHeaders)
  }

  reset<T>(agentId: string): Promise<T> {
    const agent = getAgentProfile(agentId)
    if (!agent.resetEndpoint) throw new Error(`${agent.name} does not expose reset.`)
    return httpClient.postJson<T>(agent.resetEndpoint, undefined, this.sessionHeaders)
  }

  streamMessage(agentId: string, message: string, onMessage: SseMessageHandler): Promise<void> {
    const agent = getAgentProfile(agentId)
    return sseClient.postJsonStream(
      agent.chatEndpoint,
      { message },
      onMessage,
      this.sessionHeaders,
    )
  }

  forceCooldown(agentId: string): Promise<{ ok: boolean }> {
    return this.postDebug(agentId, 'cooldown')
  }

  forceDoubleText(agentId: string): Promise<{ ok: boolean }> {
    return this.postDebug(agentId, 'doubleText')
  }

  endCooldown(agentId: string): Promise<{ ok: boolean }> {
    return this.postDebug(agentId, 'cooldownEnd')
  }

  private postDebug(
    agentId: string,
    action: 'cooldown' | 'doubleText' | 'cooldownEnd',
  ): Promise<{ ok: boolean }> {
    const agent = getAgentProfile(agentId)
    const endpoint = agent.debugEndpoints?.[action]
    if (!endpoint) throw new Error(`${agent.name} does not expose ${action}.`)
    return httpClient.postJson(endpoint, undefined, this.sessionHeaders)
  }
}

export const agentChatClient = new AgentChatClient()
