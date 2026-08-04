import type { ReactNode } from 'react'
import AgentChatView from '../views/AgentChatView/AgentChatView'
import PlaylistView from '../components/PlaylistView'
import HomeView from '../views/HomeView/HomeView'
import type { AppMode } from '../types'
import { LECTURES } from '../constants'
import type { HomeViewModel } from '../views/HomeView/useHomeViewModel'
import AgentCreateView from '../views/AgentCreateView/AgentCreateView'
import type { AgentCreateViewModel } from '../views/AgentCreateView/useAgentCreateViewModel'

export interface ViewRegistryContext {
  homeVm: HomeViewModel
  agentCreateVm: AgentCreateViewModel
  selectedAgentId: string
  selectedLectureId: string
  lectureThumbnails: Record<string, string>
  renderLessonView: () => ReactNode
  openHome: () => void
  openPlaylist: () => void
  openLecture: (lectureId: string) => void
}

export type ViewRenderer = (context: ViewRegistryContext) => ReactNode

export const viewRegistry: Record<AppMode, ViewRenderer> = {
  home: ({ homeVm }) => (
    <div className="main-layout home-layout">
      <HomeView vm={homeVm} />
    </div>
  ),
  'agent-create': ({ agentCreateVm }) => (
    <div className="main-layout agent-create-layout">
      <AgentCreateView vm={agentCreateVm} />
    </div>
  ),
  'agent-chat': ({ selectedAgentId, openHome }) => (
    <div className="main-layout">
      <AgentChatView key={selectedAgentId} agentId={selectedAgentId} onExit={openHome} />
    </div>
  ),
  playlist: ({ selectedLectureId, lectureThumbnails, openLecture }) => (
    <PlaylistView
      lectures={LECTURES}
      selectedLectureId={selectedLectureId}
      lectureThumbnails={lectureThumbnails}
      onOpenLecture={openLecture}
    />
  ),
  lesson: ({ renderLessonView }) => renderLessonView(),
}
