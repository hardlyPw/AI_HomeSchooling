import type { ReactNode } from 'react'
import FriendView from '../FriendView'
import PlaylistView from '../components/PlaylistView'
import HomeView from '../views/HomeView/HomeView'
import type { AppMode } from '../types'
import { LECTURES } from '../constants'
import type { HomeViewModel } from '../views/HomeView/useHomeViewModel'

export interface ViewRegistryContext {
  homeVm: HomeViewModel
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
  'agent-chat': ({ selectedAgentId, openHome }) => (
    <div className="main-layout">
      <FriendView agentId={selectedAgentId} onExit={openHome} />
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
