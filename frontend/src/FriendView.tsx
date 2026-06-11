import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, RotateCw } from 'lucide-react'

type Expression = 'joy' | 'happy' | 'neutral' | 'annoyed' | 'sulk'

interface FriendMessage {
  role: 'user' | 'assistant'
  text: string
  id: number
  timestamp: string
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

  const idRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/friend/state')
      .then(r => r.json())
      .then(d => { if (typeof d.affinity === 'number') setAffinity(d.affinity) })
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
    try {
      const r = await fetch('http://localhost:8000/api/v1/friend/reset', { method: 'POST' })
      const d = await r.json()
      if (typeof d.affinity === 'number') setAffinity(d.affinity)
    } catch {
      setAffinity(70)
    }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    setIsStreaming(true)
    setIsTyping(true)

    const userMsg: FriendMessage = { role: 'user', text, id: ++idRef.current, timestamp: nowHHMM() }
    setMessages(prev => [...prev, userMsg])

    const assistantId = ++idRef.current
    let assistantStarted = false

    try {
      const res = await fetch('http://localhost:8000/api/v1/friend/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
              if (typeof obj.delta === 'string') {
                if (!assistantStarted) {
                  assistantStarted = true
                  setIsTyping(false)
                  setMessages(prev => [...prev, { role: 'assistant', text: '', id: assistantId, timestamp: nowHHMM() }])
                }
                setMessages(prev => prev.map(m =>
                  m.id === assistantId ? { ...m, text: m.text + obj.delta } : m
                ))
              } else if (typeof obj.affinity === 'number') {
                setAffinity(obj.affinity)
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
    }
  }

  return (
    <div className="friend-view">
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
          <div className="friend-affinity-num">affinity {affinity}/100</div>
        )}
      </aside>

      <section className="friend-chat">
        <header className="friend-chat-header">
          <button className="friend-back" onClick={onExit} aria-label="Back to lesson">
            <ArrowLeft size={18} />
          </button>
          <div className="friend-chat-title">
            <span className="friend-name">Jiho</span>
            <span className="friend-status">online · texting</span>
          </div>
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
            className={`friend-debug-toggle ${showDebug ? 'on' : ''}`}
            onClick={() => setShowDebug(v => !v)}
            title="Toggle debug"
          >
            dbg
          </button>
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
