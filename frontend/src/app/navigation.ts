import type { AppMode } from '../types'

export type NavigationTarget =
  | { view: 'home' }
  | { view: 'agent-create' }
  | { view: 'agent-chat'; agentId: string }
  | { view: 'lesson'; lectureId?: string }
  | { view: 'playlist' }
  | { view: 'game' }

export interface NavigationController {
  currentView: AppMode
  goHome: () => void
  openCreateAgent: () => void
  openAgentChat: (agentId: string) => void
  openLesson: (lectureId?: string) => void
  openPlaylist: () => void
  openGame: () => void
}

export const viewFromTarget = (target: NavigationTarget): AppMode => {
  switch (target.view) {
    case 'home':
      return 'home'
    case 'agent-chat':
      return 'agent-chat'
    case 'agent-create':
      return 'agent-create'
    case 'lesson':
      return 'lesson'
    case 'playlist':
      return 'playlist'
    case 'game':
      return 'game'
  }
}
