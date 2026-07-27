import { LECTURES } from '../../constants'
import { listAgentProfiles } from '../../domain/agents/agentRegistry'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import type { Lecture } from '../../types'

interface UseHomeViewModelParams {
  onOpenAgent: (agentId: string) => void
  onOpenLesson: (lectureId?: string) => void
  onOpenProblemSolving: () => void
}

export interface HomeViewModel {
  agents: AgentProfile[]
  primaryLecture: Lecture
  openAgent: (agentId: string) => void
  openLesson: () => void
  openProblemSolving: () => void
}

export const useHomeViewModel = ({
  onOpenAgent,
  onOpenLesson,
  onOpenProblemSolving,
}: UseHomeViewModelParams): HomeViewModel => ({
  agents: listAgentProfiles(),
  primaryLecture: LECTURES[0],
  openAgent: onOpenAgent,
  openLesson: () => onOpenLesson(LECTURES[0].id),
  openProblemSolving: onOpenProblemSolving,
})
