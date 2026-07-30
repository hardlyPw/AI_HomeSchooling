import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, RotateCw } from 'lucide-react'

type Expression = 'joy' | 'happy' | 'neutral' | 'annoyed' | 'sulk'

interface FriendMessage {
  role: 'user' | 'assistant'
  text: string
  id: number
  timestamp: string
}

interface FriendHistoryMessage {
  role: 'user' | 'ai' | 'assistant'
  text: string
}

interface DecisionLogEntry {
  id: number
  turn: number
  timestamp: string
  user_message: string
  emotion: string
  emotion_reason: string
  timing: string
  action: string
  affinity_prev: number
  affinity_next: number
  affinity_delta: number
  affinity_reason: string
  reasoning: string
  away_mode: string
  response_seconds: number | null
  decision_prompt_tokens: number | null
  decision_completion_tokens: number | null
  reply_prompt_tokens: number | null
  reply_completion_tokens: number | null
  total_tokens: number | null
}

function nowHHMM(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

const EXPRESSION_SRC: Record<Expression, string> = {
  joy: '/assets/jiho/jiho_joy.png',
  happy: '/assets/jiho/jiho_happy.png',
  neutral: '/assets/jiho/jiho_neutral.png',
  annoyed: '/assets/jiho/jiho_annoyed.png',
  sulk: '/assets/jiho/jiho_sulk.png',
}

const FRIEND_SESSION_STORAGE_KEY = 'ai-homeschooling.friend-session-id'

function getOrCreateFriendSessionId(): string {
  const existing = window.localStorage.getItem(FRIEND_SESSION_STORAGE_KEY)
  if (existing) return existing

  const generated = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  window.localStorage.setItem(FRIEND_SESSION_STORAGE_KEY, generated)
  return generated
}

function affinityToExpression(a: number): Expression {
  if (a >= 85) return 'joy'
  if (a >= 60) return 'happy'
  if (a >= 35) return 'neutral'
  if (a >= 15) return 'annoyed'
  return 'sulk'
}

interface Props {
  onExit: () => void
}

export default function FriendView({ onExit }: Props) {
  const [messages, setMessages] = useState<FriendMessage[]>([])
  const [input, setInput] = useState('')
  const [affinity, setAffinity] = useState(70)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [showDebug, setShowDebug] = useState(false)
  const [cooldownArmed, setCooldownArmed] = useState(false)
  const [doubleTextArmed, setDoubleTextArmed] = useState(false)
  const [isOnline, setIsOnline] = useState(true)
  const [decisionLog, setDecisionLog] = useState<DecisionLogEntry[]>([])

  const idRef = useRef(0)
  const sessionIdRef = useRef(getOrCreateFriendSessionId())
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/friend/history', {
      headers: { 'X-Session-ID': sessionIdRef.current },
    })
      .then(r => r.json())
      .then(d => {
        if (typeof d.affinity === 'number') setAffinity(d.affinity)
        if (Array.isArray(d.messages)) {
          const restored = d.messages
            .filter((m: FriendHistoryMessage) => m.role === 'user' || m.role === 'ai' || m.role === 'assistant')
            .map((m: FriendHistoryMessage, index: number) => ({
              role: m.role === 'user' ? 'user' : 'assistant',
              text: m.text,
              id: index + 1,
              timestamp: nowHHMM(),
            }))
          idRef.current = restored.length
          setMessages(restored)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isTyping])

  const expression = affinityToExpression(affinity)

  const reset = async () => {
    if (isStreaming) return
    setMessages([])
    setCooldownArmed(false)
    setDoubleTextArmed(false)
    setIsOnline(true)
    setDecisionLog([])
    try {
      const r = await fetch('http://localhost:8000/api/v1/friend/reset', {
        method: 'POST',
        headers: { 'X-Session-ID': sessionIdRef.current },
      })
      const d = await r.json()
      if (typeof d.affinity === 'number') setAffinity(d.affinity)
    } catch {
      setAffinity(70)
    }
  }

  const forceCooldown = async () => {
    if (isStreaming) return
    try {
      await fetch('http://localhost:8000/api/v1/friend/debug/cooldown', {
        method: 'POST',
        headers: { 'X-Session-ID': sessionIdRef.current },
      })
      setCooldownArmed(true)
    } catch {
      // Debug helper only; keep the demo UI calm if the backend is not reachable.
    }
  }

  const forceDoubleText = async () => {
    if (isStreaming) return
    try {
      await fetch('http://localhost:8000/api/v1/friend/debug/double-text', {
        method: 'POST',
        headers: { 'X-Session-ID': sessionIdRef.current },
      })
      setDoubleTextArmed(true)
    } catch {
      // Debug helper only; keep the demo UI calm if the backend is not reachable.
    }
  }

  const endCooldown = async () => {
    try {
      await fetch('http://localhost:8000/api/v1/friend/debug/cooldown-end', {
        method: 'POST',
        headers: { 'X-Session-ID': sessionIdRef.current },
      })
    } catch {
      // Debug helper only; keep the demo UI calm if the backend is not reachable.
    }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    setCooldownArmed(false)
    setDoubleTextArmed(false)
    setIsStreaming(true)
    setIsTyping(true)

    const userMsg: FriendMessage = { role: 'user', text, id: ++idRef.current, timestamp: nowHHMM() }
    setMessages(prev => [...prev, userMsg])

    const assistantId = ++idRef.current
    let activeAssistantId = assistantId
    let assistantStarted = false

    try {
      const res = await fetch('http://localhost:8000/api/v1/friend/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionIdRef.current,
        },
        body: JSON.stringify({ message: text }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })

        let sep
        while ((sep = buf.indexOf('\n\n')) !== -1) {
          const raw = buf.slice(0, sep)
          buf = buf.slice(sep + 2)
          for (const line of raw.split('\n')) {
            if (!line.startsWith('data: ')) continue
            const data = line.slice(6)
            try {
              const obj = JSON.parse(data)
              if (obj.message_break) {
                activeAssistantId = ++idRef.current
                assistantStarted = true
                setIsTyping(false)
                const nextAssistantId = activeAssistantId
                setMessages(prev => [...prev, { role: 'assistant', text: '', id: nextAssistantId, timestamp: nowHHMM() }])
              } else if (typeof obj.delta === 'string') {
                setIsOnline(true)
                const targetAssistantId = activeAssistantId
                if (!assistantStarted) {
                  assistantStarted = true
                  setIsTyping(false)
                  setMessages(prev => [...prev, { role: 'assistant', text: '', id: targetAssistantId, timestamp: nowHHMM() }])
                }
                setMessages(prev => prev.map(m =>
                  m.id === targetAssistantId ? { ...m, text: m.text + obj.delta } : m
                ))
              } else if (typeof obj.affinity === 'number') {
                setAffinity(obj.affinity)
              } else if (obj.decision) {
                const d = obj.decision
                setDecisionLog(prev => [...prev, {
                  id: ++idRef.current,
                  turn: prev.length + 1,
                  timestamp: nowHHMM(),
                  user_message: String(d.user_message ?? ''),
                  emotion: String(d.emotion ?? ''),
                  emotion_reason: String(d.emotion_reason ?? ''),
                  timing: String(d.timing ?? ''),
                  action: String(d.action ?? ''),
                  affinity_prev: Number(d.affinity_prev ?? 0),
                  affinity_next: Number(d.affinity_next ?? 0),
                  affinity_delta: Number(d.affinity_delta ?? 0),
                  affinity_reason: String(d.affinity_reason ?? ''),
                  reasoning: String(d.reasoning ?? ''),
                  away_mode: String(d.away_mode ?? ''),
                  response_seconds: null,
                  decision_prompt_tokens: null,
                  decision_completion_tokens: null,
                  reply_prompt_tokens: null,
                  reply_completion_tokens: null,
                  total_tokens: null,
                }])
              } else if (obj.timing && typeof obj.timing.total_seconds === 'number') {
                const secs = obj.timing.total_seconds
                setDecisionLog(prev => {
                  if (prev.length === 0) return prev
                  const next = prev.slice()
                  next[next.length - 1] = { ...next[next.length - 1], response_seconds: secs }
                  return next
                })
              } else if (obj.tokens) {
                const tk = obj.tokens
                setDecisionLog(prev => {
                  if (prev.length === 0) return prev
                  const next = prev.slice()
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    decision_prompt_tokens: typeof tk.decision_prompt === 'number' ? tk.decision_prompt : null,
                    decision_completion_tokens: typeof tk.decision_completion === 'number' ? tk.decision_completion : null,
                    reply_prompt_tokens: typeof tk.reply_prompt === 'number' ? tk.reply_prompt : null,
                    reply_completion_tokens: typeof tk.reply_completion === 'number' ? tk.reply_completion : null,
                    total_tokens: typeof tk.total === 'number' ? tk.total : null,
                  }
                  return next
                })
              } else if (obj.status === 'cooldown') {
                setIsOnline(false)
                setIsTyping(false)
              } else if (obj.status === 'delayed') {
                setIsTyping(true)
              } else if (obj.error) {
                setMessages(prev => [...prev, {
                  role: 'assistant',
                  text: `⚠️ ${obj.error}`,
                  id: ++idRef.current,
                  timestamp: nowHHMM(),
                }])
              }
            } catch { /* ignore */ }
          }
        }
      }
    } catch (err) {
      console.error(err)
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: '⚠️ Connection failed.',
        id: ++idRef.current,
        timestamp: nowHHMM(),
      }])
    } finally {
      setIsStreaming(false)
      setIsTyping(false)
      setIsOnline(true)
    }
  }

  return (
    <div className="friend-view">
      {showDebug && (
        <div className="friend-decision-log">
          <div className="friend-decision-log-header">
            <span>decision log ({decisionLog.length})</span>
            <button
              className="friend-decision-log-clear"
              onClick={() => setDecisionLog([])}
              disabled={decisionLog.length === 0}
            >
              clear
            </button>
          </div>
          <div className="friend-decision-log-body">
            {decisionLog.length === 0 && (
              <div className="friend-decision-log-empty">no turns yet</div>
            )}
            {decisionLog.slice().reverse().map(entry => (
              <div key={entry.id} className="friend-decision-entry">
                <div className="friend-decision-row top">
                  <span className="friend-decision-turn">#{entry.turn}</span>
                  <span className="friend-decision-time">{entry.timestamp}</span>
                  {entry.response_seconds != null && (
                    <span className="friend-decision-tag latency">{entry.response_seconds.toFixed(2)}s</span>
                  )}
                  {entry.away_mode && entry.away_mode !== 'normal' && (
                    <span className="friend-decision-tag away">{entry.away_mode}</span>
                  )}
                </div>
                <div className="friend-decision-user">› {entry.user_message}</div>
                <div className="friend-decision-row">
                  <span className="friend-decision-tag emo">{entry.emotion || '—'}</span>
                  <span className="friend-decision-tag timing">{entry.timing || '—'}</span>
                  {entry.action && entry.action !== 'normal' && (
                    <span className="friend-decision-tag action">{entry.action}</span>
                  )}
                </div>
                {entry.emotion_reason && (
                  <div className="friend-decision-reason">why: {entry.emotion_reason}</div>
                )}
                <div className="friend-decision-row">
                  <span className={`friend-decision-aff ${entry.affinity_delta > 0 ? 'up' : entry.affinity_delta < 0 ? 'down' : ''}`}>
                    aff {entry.affinity_prev}→{entry.affinity_next} ({entry.affinity_delta >= 0 ? '+' : ''}{entry.affinity_delta})
                  </span>
                </div>
                {entry.affinity_reason && (
                  <div className="friend-decision-reason">{entry.affinity_reason}</div>
                )}
                {entry.total_tokens != null && (
                  <div className="friend-decision-tokens">
                    <span className="friend-decision-tag tok-total">{entry.total_tokens} tok</span>
                    {entry.decision_prompt_tokens != null && entry.decision_completion_tokens != null && (
                      <span className="friend-decision-tok-part">
                        decision {entry.decision_prompt_tokens}+{entry.decision_completion_tokens}
                      </span>
                    )}
                    {entry.reply_prompt_tokens != null && entry.reply_completion_tokens != null && (
                      <span className="friend-decision-tok-part">
                        reply {entry.reply_prompt_tokens}+{entry.reply_completion_tokens}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <aside className={`friend-stage stage-${expression}`}>
        <div className="friend-stage-inner">
          {(['joy', 'happy', 'neutral', 'annoyed', 'sulk'] as Expression[]).map(exp => (
            <img
              key={exp}
              src={EXPRESSION_SRC[exp]}
              alt={`Jiho ${exp}`}
              className={`friend-portrait ${expression === exp ? 'active' : ''}`}
              draggable={false}
            />
          ))}
        </div>

        {showDebug && (
          <div className="friend-affinity-num">
            affinity {affinity}/100{cooldownArmed ? ' | next cooldown armed' : ''}{doubleTextArmed ? ' | next double-text armed' : ''}
          </div>
        )}
      </aside>

      <section className="friend-chat">
        <header className="friend-chat-header">
          <button className="friend-back" onClick={onExit} aria-label="Back to lesson">
            <ArrowLeft size={18} />
          </button>
          <div className="friend-chat-title">
            <span className="friend-name">Jiho</span>
            <span className={`friend-status ${isOnline ? 'online' : 'offline'}`}>
              <span className="friend-status-dot" />
              {isOnline ? 'online' : 'offline'}
            </span>
          </div>
          <button
            className={`friend-debug-toggle ${showDebug ? 'on' : ''}`}
            onClick={() => setShowDebug(v => !v)}
            title="Toggle debug"
          >
            dbg
          </button>
          {showDebug && (
            <>
              <button
                className="friend-reset"
                onClick={reset}
                disabled={isStreaming}
                aria-label="Reset conversation"
                title="Reset conversation"
              >
                <RotateCw size={16} />
              </button>
              <button
                className="friend-debug-toggle"
                onClick={forceCooldown}
                disabled={isStreaming}
                title="Force cooldown on next message"
              >
                cooldown
              </button>
              <button
                className="friend-debug-toggle"
                onClick={endCooldown}
                title="Skip the active cooldown wait"
              >
                cooldown_end
              </button>
              <button
                className="friend-debug-toggle"
                onClick={forceDoubleText}
                disabled={isStreaming}
                title="Force double-text on next message"
              >
                double
              </button>
            </>
          )}
          <button className="friend-go-class" onClick={onExit}>
            Go to class
          </button>
        </header>

        <div className="friend-chat-window" ref={scrollRef}>
          {messages.map(m => (
            <div key={m.id} className={`friend-row ${m.role}`}>
              {m.role === 'user' && <span className="friend-bubble-time">{m.timestamp}</span>}
              <div className={`friend-bubble ${m.role}`}>
                {m.text || (m.role === 'assistant' && isTyping ? '…' : '')}
              </div>
              {m.role === 'assistant' && <span className="friend-bubble-time">{m.timestamp}</span>}
            </div>
          ))}
          {isTyping && (
            <div className="friend-bubble assistant typing">
              <span></span><span></span><span></span>
            </div>
          )}
        </div>

        <div className="friend-input-area">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Send a message…"
            disabled={isStreaming}
          />
          <button onClick={send} disabled={isStreaming || !input.trim()}>
            Send
          </button>
        </div>
      </section>
    </div>
  )
}
