import { useCallback, useEffect, useState } from 'react'
import { agentCatalogClient } from '../../clients/agents/AgentCatalogClient'
import { LECTURES } from '../../constants'
import {
  listAgentProfiles,
  removeAgentProfile,
  upsertAgentProfiles,
} from '../../domain/agents/agentRegistry'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import type { Lecture } from '../../types'

interface UseHomeViewModelParams {
  onOpenAgent: (agentId: string) => void
  onOpenCreateAgent: () => void
  onOpenLesson: (lectureId?: string) => void
  onOpenProblemSolving: () => void
  onOpenGame: () => void
}

export interface HomeViewModel {
  agents: AgentProfile[]
  isLoadingAgents: boolean
  agentLoadError: string
  deletingAgentId: string
  pendingDeleteId: string
  primaryLecture: Lecture
  openAgent: (agentId: string) => void
  openCreateAgent: () => void
  refreshAgents: () => Promise<void>
  openLesson: () => void
  openProblemSolving: () => void
  openGame: () => void
  cancelDeleteAgent: () => void
  confirmDeleteAgent: () => Promise<void>
  requestDeleteAgent: (agentId: string) => void
}

export const useHomeViewModel = ({
  onOpenAgent,
  onOpenCreateAgent,
  onOpenLesson,
  onOpenProblemSolving,
  onOpenGame,
}: UseHomeViewModelParams): HomeViewModel => {
  const [agents, setAgents] = useState<AgentProfile[]>(listAgentProfiles())
  const [isLoadingAgents, setIsLoadingAgents] = useState(true)
  const [agentLoadError, setAgentLoadError] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState('')
  const [deletingAgentId, setDeletingAgentId] = useState('')

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

  const confirmDeleteAgent = async () => {
    if (!pendingDeleteId || deletingAgentId) return
    const agentId = pendingDeleteId
    setDeletingAgentId(agentId)
    setAgentLoadError('')
    try {
      await agentCatalogClient.deleteAgent(agentId)
      removeAgentProfile(agentId)
      setAgents(listAgentProfiles())
      setPendingDeleteId('')
    } catch {
      setAgentLoadError('Could not delete this Agent.')
    } finally {
      setDeletingAgentId('')
    }
  }

  return {
    agents,
    isLoadingAgents,
    agentLoadError,
    deletingAgentId,
    pendingDeleteId,
    primaryLecture: LECTURES[0],
    openAgent: onOpenAgent,
    openCreateAgent: onOpenCreateAgent,
    refreshAgents,
    openLesson: () => onOpenLesson(LECTURES[0].id),
    openProblemSolving: onOpenProblemSolving,
    openGame: onOpenGame,
    cancelDeleteAgent: () => setPendingDeleteId(''),
    confirmDeleteAgent,
    requestDeleteAgent: setPendingDeleteId,
  }
}
