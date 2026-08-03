const FRIEND_SESSION_STORAGE_KEY = 'ai-homeschooling.friend-session-id'
const FRIEND_USER_STORAGE_KEY = 'ai-homeschooling.user-id'

function createBrowserId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function getOrCreateFriendSessionId(): string {
  const existing = window.localStorage.getItem(FRIEND_SESSION_STORAGE_KEY)
  if (existing) return existing

  const generated = createBrowserId()
  window.localStorage.setItem(FRIEND_SESSION_STORAGE_KEY, generated)
  return generated
}

export function getOrCreateFriendUserId(): string {
  const existing = window.localStorage.getItem(FRIEND_USER_STORAGE_KEY)
  if (existing) return existing

  const generated = createBrowserId()
  window.localStorage.setItem(FRIEND_USER_STORAGE_KEY, generated)
  return generated
}
