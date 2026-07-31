import type { AppMode } from '../types'

export type NavigationTarget =
  | { view: 'home' }
  | { view: 'agent-chat'; agentId: string }
  | { view: 'lesson'; lectureId?: string }
  | { view: 'playlist' }

export interface NavigationController {
  currentView: AppMode
  goHome: () => void
  openAgentChat: (agentId: string) => void
  openLesson: (lectureId?: string) => void
  openPlaylist: () => void
}

export const viewFromTarget = (target: NavigationTarget): AppMode => {
  switch (target.view) {
    case 'home':
      return 'home'
    case 'agent-chat':
      return 'agent-chat'
    case 'lesson':
      return 'lesson'
    case 'playlist':
      return 'playlist'
  }
}
