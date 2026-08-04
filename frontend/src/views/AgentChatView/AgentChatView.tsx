import { ArrowLeft, Bot, RotateCw } from 'lucide-react'
import { useAgentChatViewModel, type AgentExpression } from './useAgentChatViewModel'

const EXPRESSION_SRC: Record<AgentExpression, string> = {
  joy: '/assets/jiho/jiho_joy.png',
  happy: '/assets/jiho/jiho_happy.png',
  neutral: '/assets/jiho/jiho_neutral.png',
  annoyed: '/assets/jiho/jiho_annoyed.png',
  sulk: '/assets/jiho/jiho_sulk.png',
}

const EXPRESSIONS = Object.keys(EXPRESSION_SRC) as AgentExpression[]

interface AgentChatViewProps {
  agentId: string
  onExit: () => void
}

export default function AgentChatView({ agentId, onExit }: AgentChatViewProps) {
  const {
    agent,
    affinity,
    bindInput,
    bindScrollContainer,
    canDebug,
    clearDecisionLog,
    cooldownArmed,
    decisionLog,
    doubleTextArmed,
    endCooldown,
    expression,
    forceCooldown,
    forceDoubleText,
    hasAvatar,
    input,
    isOnline,
    isStreaming,
    isTyping,
    messages,
    reset,
    send,
    setInput,
    showDebug,
    toggleDebug,
  } = useAgentChatViewModel(agentId)

  return (
    <div className="friend-view">
      {showDebug && (
        <div className="friend-decision-log">
          <div className="friend-decision-log-header">
            <span>decision log ({decisionLog.length})</span>
            <button
              className="friend-decision-log-clear"
              onClick={clearDecisionLog}
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
                <div className="friend-decision-user">user: {entry.user_message}</div>
                <div className="friend-decision-row">
                  <span className="friend-decision-tag emo">{entry.emotion || '-'}</span>
                  <span className="friend-decision-tag timing">{entry.timing || '-'}</span>
                  {entry.action && entry.action !== 'normal' && (
                    <span className="friend-decision-tag action">{entry.action}</span>
                  )}
                </div>
                {entry.emotion_reason && (
                  <div className="friend-decision-reason">why: {entry.emotion_reason}</div>
                )}
                <div className="friend-decision-row">
                  <span className={`friend-decision-aff ${entry.affinity_delta > 0 ? 'up' : entry.affinity_delta < 0 ? 'down' : ''}`}>
                    aff {entry.affinity_prev} -&gt; {entry.affinity_next} ({entry.affinity_delta >= 0 ? '+' : ''}{entry.affinity_delta})
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
          {hasAvatar ? (
            EXPRESSIONS.map(mood => (
              <img
                key={mood}
                src={agent.avatarByMood?.[mood] ?? EXPRESSION_SRC[mood]}
                alt={`${agent.name} ${mood}`}
                className={`friend-portrait ${expression === mood ? 'active' : ''}`}
                draggable={false}
              />
            ))
          ) : (
            <div className="friend-portrait-placeholder" aria-label={`${agent.name} avatar`}>
              <Bot size={52} />
              <strong>{agent.name.slice(0, 2).toUpperCase()}</strong>
            </div>
          )}
        </div>

        {showDebug && (
          <div className="friend-affinity-num">
            affinity {affinity}/100{cooldownArmed ? ' | next cooldown armed' : ''}{doubleTextArmed ? ' | next double-text armed' : ''}
          </div>
        )}
      </aside>

      <section className="friend-chat">
        <header className="friend-chat-header">
          <button className="friend-back" onClick={onExit} aria-label="Back to home">
            <ArrowLeft size={18} />
          </button>
          <div className="friend-chat-title">
            <span className="friend-name">{agent.name}</span>
            <span className={`friend-status ${isOnline ? 'online' : 'offline'}`}>
              <span className="friend-status-dot" />
              {isOnline ? 'online' : 'offline'}
            </span>
          </div>
          {canDebug && (
            <button
              className={`friend-debug-toggle ${showDebug ? 'on' : ''}`}
              onClick={toggleDebug}
              title="Toggle debug"
            >
              dbg
            </button>
          )}
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
          <button className="friend-go-class" onClick={onExit}>Go to class</button>
        </header>

        <div className="friend-chat-window" ref={bindScrollContainer}>
          {messages.map(message => (
            <div key={message.id} className={`friend-row ${message.role}`}>
              {message.role === 'user' && <span className="friend-bubble-time">{message.timestamp}</span>}
              <div className={`friend-bubble ${message.role}`}>
                {message.text || (message.role === 'assistant' && isTyping ? '...' : '')}
              </div>
              {message.role === 'assistant' && <span className="friend-bubble-time">{message.timestamp}</span>}
            </div>
          ))}
          {isTyping && (
            <div className="friend-bubble assistant typing">
              <span /><span /><span />
            </div>
          )}
        </div>

        <div className="friend-input-area">
          <input
            ref={bindInput}
            value={input}
            onChange={event => setInput(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            placeholder="Send a message..."
            disabled={isStreaming}
          />
          <button onClick={() => void send()} disabled={isStreaming || !input.trim()}>
            Send
          </button>
        </div>
      </section>
    </div>
  )
}
