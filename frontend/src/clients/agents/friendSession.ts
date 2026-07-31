const FRIEND_SESSION_STORAGE_KEY = 'ai-homeschooling.friend-session-id'

export function getOrCreateFriendSessionId(): string {
  const existing = window.localStorage.getItem(FRIEND_SESSION_STORAGE_KEY)
  if (existing) return existing

  const generated = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  window.localStorage.setItem(FRIEND_SESSION_STORAGE_KEY, generated)
  return generated
}
