import { ArrowLeft, Brain, Check, CheckCircle2, Clock3, LoaderCircle, MessageCircle, Play, RotateCcw, UserRound, XCircle } from 'lucide-react'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import { useMemoryMatchViewModel } from './useMemoryMatchViewModel'

interface MemoryMatchViewProps {
  agents: AgentProfile[]
  onExit: () => void
}

const quickChats = ['Good luck!', 'Nice one!', 'Watch this!', 'So close!', 'Good game!']

export default function MemoryMatchView({ agents, onExit }: MemoryMatchViewProps) {
  const vm = useMemoryMatchViewModel(agents)

  if (!vm.state) {
    return (
      <main className="memory-game lobby">
        <header className="game-hub-header">
          <button className="icon-button" onClick={onExit} aria-label="Back" title="Back"><ArrowLeft /></button>
          <div><span className="game-eyebrow">Play with a friend</span><h1>Memory Match</h1></div>
        </header>
        <section className="memory-lobby-content">
          <div className="memory-card-preview" aria-hidden="true">{Array.from({ length: 12 }, (_, index) => <span key={index}>{(index % 6) + 1}</span>)}</div>
          <div className="memory-lobby-setup">
            <h2>Choose your opponent</h2>
            <div className="opponent-list" role="radiogroup" aria-label="Opponent">
              {agents.map(agent => (
                <button key={agent.id} className={vm.selectedAgentId === agent.id ? 'opponent-option simple selected' : 'opponent-option simple'} onClick={() => vm.setSelectedAgentId(agent.id)} role="radio" aria-checked={vm.selectedAgentId === agent.id} disabled={vm.isBusy}>
                  <span className="opponent-avatar">{agent.avatarByMood?.happy ? <img src={agent.avatarByMood.happy} alt="" /> : <Brain size={22} />}</span>
                  <span className="opponent-name"><strong>{agent.name}</strong><small className={`agent-presence ${agent.isOnline ? 'online' : 'offline'}`}><i />{agent.isOnline ? 'Online' : 'Offline'}</small></span>
                  {vm.selectedAgentId === agent.id && <Check size={20} aria-hidden="true" />}
                </button>
              ))}
            </div>
            {vm.error && <p className="game-error">{vm.error}</p>}
            {vm.challengePending ? (
              <div className="memory-challenge-status" role="status">
                <LoaderCircle size={20} />
                <span><strong>Challenge sent</strong><small>Waiting for {vm.selectedAgent?.name ?? 'your opponent'} to accept...</small></span>
              </div>
            ) : (
              <button className="game-primary-button" onClick={() => void vm.start()} disabled={vm.isBusy || !agents.length}><Play size={18} /> Start duel</button>
            )}
          </div>
        </section>
        {vm.challengeDecision && (
          <div className={`challenge-result-backdrop ${vm.challengeDecision}`} onClick={vm.dismissRejectedChallenge} role="presentation">
            <section className="challenge-result-dialog" role="dialog" aria-modal="true" aria-labelledby="challenge-result-title" onClick={event => event.stopPropagation()}>
              {vm.challengeDecision === 'accepted' ? <CheckCircle2 size={38} /> : <XCircle size={38} />}
              <h2 id="challenge-result-title">{vm.selectedAgent?.name} {vm.challengeDecision === 'accepted' ? 'accepted your challenge.' : 'declined your challenge.'}</h2>
              <p>{vm.challengeDecision === 'accepted' ? 'Entering the game...' : 'Your friend is currently offline.'}</p>
              {vm.challengeDecision === 'accepted' && <LoaderCircle className="challenge-result-spinner" size={20} />}
              {vm.challengeDecision === 'rejected' && <small>Click outside to close</small>}
            </section>
          </div>
        )}
      </main>
    )
  }

  const gameState = vm.state
  const complete = gameState.phase === 'completed'
  return (
    <main className="memory-game playing">
      <header className="memory-game-header">
        <button className="icon-button" onClick={onExit} aria-label="Exit game" title="Exit game"><ArrowLeft /></button>
        <div><span className="game-eyebrow">Memory Match</span><h1>{complete ? 'Match complete' : vm.isRoomCountdown ? `Get ready · ${vm.roomRemaining}s` : vm.state.phase === 'preview' ? `Memorize · ${vm.previewRemaining}s` : vm.isBusy ? `${vm.state.agent_name} is playing` : `Your turn · ${vm.turnRemaining}s`}</h1></div>
        {!complete && !vm.isBusy && <span className={(vm.showFlipWarning || (vm.turnRemaining <= 5 && vm.state.phase === 'player_turn')) ? 'timer urgent' : 'timer'}><Clock3 size={16} /> {vm.isRoomCountdown ? vm.roomRemaining : vm.state.phase === 'preview' ? vm.previewRemaining : vm.turnRemaining}s</span>}
      </header>

      <section className="memory-arena">
        <PlayerStation
          position="agent"
          name={vm.state.agent_name}
          score={vm.displayAgentScore}
          bubble={vm.agentBubble}
          avatar={vm.selectedAgent?.avatarByMood?.happy}
        />

        <div className="memory-board-stage">
          <MemoryStageNotice side="left" roomRemaining={vm.roomRemaining} previewRemaining={vm.previewRemaining} isRoomCountdown={vm.isRoomCountdown} showFlipWarning={vm.showFlipWarning} />
          <div className={`memory-board ${vm.isBusy ? 'agent-acting' : ''}`} aria-label="Memory card board">
            {vm.state.cards.map(card => {
              const revealed = vm.isRevealed(card.index)
              return (
                <button
                  key={card.index}
                  className={`memory-card ${revealed ? 'revealed' : ''} ${vm.isMatched(card.index) ? 'matched' : ''}`}
                  onClick={() => void vm.chooseCard(card.index)}
                  disabled={gameState.phase !== 'player_turn' || vm.isBusy || vm.isMatched(card.index)}
                  aria-label={revealed ? `Card ${card.index + 1}, value ${vm.cardValue(card.index)}` : `Hidden card ${card.index + 1}`}
                >
                  <span className="memory-card-back"><Brain size={18} /></span>
                  <span className="memory-card-face">{revealed ? vm.cardValue(card.index) : ''}</span>
                </button>
              )
            })}
          </div>
          <MemoryStageNotice side="right" roomRemaining={vm.roomRemaining} previewRemaining={vm.previewRemaining} isRoomCountdown={vm.isRoomCountdown} showFlipWarning={vm.showFlipWarning} />
        </div>

        <div className="player-station-wrap">
          {vm.quickMenuOpen && (
            <div className="memory-quick-menu">
              {quickChats.map(text => <button key={text} onClick={() => vm.sendQuickChat(text)}>{text}</button>)}
            </div>
          )}
          <button className="player-station player interactive" onClick={() => vm.setQuickMenuOpen(!vm.quickMenuOpen)} aria-label="Open quick chat">
            {vm.userBubble && <span className="character-bubble user">{vm.userBubble}</span>}
            <span className="player-avatar fallback"><UserRound size={30} /></span>
            <span><strong>You</strong><small><MessageCircle size={13} /> Quick chat</small></span>
            <b>{vm.state.user_score}</b>
          </button>
        </div>
      </section>

      {complete && (
        <div className="memory-result-overlay">
          <section>
            <span className="game-eyebrow">Final score</span>
            <h2>{vm.state.winner === 'user' ? 'You won!' : vm.state.winner === 'agent' ? `${vm.state.agent_name} won` : 'Draw game'}</h2>
            <div className="memory-final-score"><strong>{vm.state.user_score}</strong><span>You · {vm.state.agent_name}</span><strong>{vm.state.agent_score}</strong></div>
            <div className="summary-actions"><button className="game-secondary-button" onClick={onExit}><ArrowLeft size={17} /> Games</button><button className="game-primary-button" onClick={vm.restart}><RotateCcw size={17} /> Play again</button></div>
          </section>
        </div>
      )}
    </main>
  )
}

function MemoryStageNotice({ side, roomRemaining, previewRemaining, isRoomCountdown, showFlipWarning }: { side: 'left' | 'right'; roomRemaining: number; previewRemaining: number; isRoomCountdown: boolean; showFlipWarning: boolean }) {
  const visible = isRoomCountdown || showFlipWarning
  return (
    <aside className={`memory-stage-notice ${side} ${visible ? 'visible' : ''}`} aria-live="polite">
      {isRoomCountdown && <><strong>The game will start soon.</strong><span>Remember the numbers!</span><b>{roomRemaining}s</b></>}
      {showFlipWarning && <><strong>Cards will flip soon!</strong><span>Keep memorizing.</span><b>{previewRemaining}s</b></>}
    </aside>
  )
}

function PlayerStation({ name, score, bubble, avatar, position }: { name: string; score: number; bubble: string; avatar?: string; position: 'agent' }) {
  return (
    <div className={`player-station ${position}`}>
      {bubble && <span className="character-bubble agent">{bubble}</span>}
      <span className="player-avatar">{avatar ? <img src={avatar} alt="" /> : <Brain size={30} />}</span>
      <span><strong>{name}</strong><small>Opponent</small></span>
      <b>{score}</b>
    </div>
  )
}
