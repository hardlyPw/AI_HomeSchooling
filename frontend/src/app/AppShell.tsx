import type { AppMode } from '../types'
import { viewRegistry, type ViewRegistryContext } from './viewRegistry'

interface AppShellProps extends ViewRegistryContext {
  currentView: AppMode
}

export default function AppShell({ currentView, ...context }: AppShellProps) {
  return viewRegistry[currentView](context)
}
