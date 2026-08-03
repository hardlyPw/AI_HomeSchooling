import { useCallback, useEffect, useState } from 'react'
import { agentCatalogClient } from '../../clients/agents/AgentCatalogClient'
import { LECTURES } from '../../constants'
import { listAgentProfiles, upsertAgentProfiles } from '../../domain/agents/agentRegistry'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import type { Lecture } from '../../types'

interface UseHomeViewModelParams {
  onOpenAgent: (agentId: string) => void
  onOpenCreateAgent: () => void
  onOpenLesson: (lectureId?: string) => void
  onOpenProblemSolving: () => void
}

export interface HomeViewModel {
  agents: AgentProfile[]
  isLoadingAgents: boolean
  agentLoadError: string
  primaryLecture: Lecture
  openAgent: (agentId: string) => void
  openCreateAgent: () => void
  refreshAgents: () => Promise<void>
  openLesson: () => void
  openProblemSolving: () => void
}

export const useHomeViewModel = ({
  onOpenAgent,
  onOpenCreateAgent,
  onOpenLesson,
  onOpenProblemSolving,
}: UseHomeViewModelParams): HomeViewModel => {
  const [agents, setAgents] = useState<AgentProfile[]>(listAgentProfiles())
  const [isLoadingAgents, setIsLoadingAgents] = useState(true)
  const [agentLoadError, setAgentLoadError] = useState('')

  const refreshAgents = useCallback(async () => {
    setIsLoadingAgents(true)
    setAgentLoadError('')
    try {
      const profiles = await agentCatalogClient.listAgents()
      upsertAgentProfiles(profiles)
      setAgents(listAgentProfiles())
    } catch {
      setAgentLoadError('Agent list is temporarily unavailable.')
      setAgents(listAgentProfiles())
    } finally {
      setIsLoadingAgents(false)
    }
  }, [])

  useEffect(() => {
    let isActive = true
    agentCatalogClient
      .listAgents()
      .then(profiles => {
        if (!isActive) return
        upsertAgentProfiles(profiles)
        setAgents(listAgentProfiles())
      })
      .catch(() => {
        if (!isActive) return
        setAgentLoadError('Agent list is temporarily unavailable.')
      })
      .finally(() => {
        if (isActive) setIsLoadingAgents(false)
      })
    return () => {
      isActive = false
    }
  }, [])

  return {
    agents,
    isLoadingAgents,
    agentLoadError,
    primaryLecture: LECTURES[0],
    openAgent: onOpenAgent,
    openCreateAgent: onOpenCreateAgent,
    refreshAgents,
    openLesson: () => onOpenLesson(LECTURES[0].id),
    openProblemSolving: onOpenProblemSolving,
  }
}
