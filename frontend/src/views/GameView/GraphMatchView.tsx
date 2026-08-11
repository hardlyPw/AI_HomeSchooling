import { ArrowLeft, ChevronRight, Clock3, Minus, Play, Plus, RotateCcw, Send, Trophy } from 'lucide-react'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import FunctionGraph from './FunctionGraph'
import MathFormula from './MathFormula'
import { useGraphMatchViewModel } from './useGraphMatchViewModel'

interface GraphMatchViewProps {
  agents: AgentProfile[]
  onExit: () => void
}

const quickChats = [
  ['hello', 'Hello!'],
  ['nice', 'Nice one!'],
  ['try_harder', 'Step it up!'],
  ['great_play', 'Great play!'],
  ['close', 'So close!'],
  ['good_game', 'Good game!'],
] as const

const baseOptions = [1 / 3, 1 / 2, 2, 3]

export default function GraphMatchView({ agents, onExit }: GraphMatchViewProps) {
  const vm = useGraphMatchViewModel(agents)
  const round = vm.state?.current_round

  if (!vm.state) {
    return (
      <main className="graph-game lobby">
        <header className="graph-game-header">
          <button className="icon-button" onClick={onExit} aria-label="Back" title="Back"><ArrowLeft /></button>
          <div><span className="game-eyebrow">Educational game</span><h1>Graph Match</h1></div>
        </header>
        <section className="game-lobby-content">
          <div className="game-lobby-visual" aria-hidden="true">
            <span className="curve curve-one" />
            <span className="curve curve-two" />
            <div className="game-lobby-formula"><MathFormula latex="f(x)=a\cdot b^{x-h}+k" block /></div>
          </div>
          <div className="game-lobby-setup">
            <h2>Choose your opponent</h2>
            <div className="opponent-list" role="radiogroup" aria-label="Opponent">
              {agents.map(agent => (
                <button
                  key={agent.id}
                  className={vm.selectedAgentId === agent.id ? 'opponent-option selected' : 'opponent-option'}
                  onClick={() => vm.setSelectedAgentId(agent.id)}
                  role="radio"
                  aria-checked={vm.selectedAgentId === agent.id}
                >
                  <span><strong>{agent.name}</strong><small>{agent.description}</small></span>
                  <span className={`skill-badge ${agent.gameSkillTier}`}>{agent.gameSkillTier}</span>
                </button>
              ))}
            </div>
            <div className="game-rule-strip">
              <span>3 rounds</span><span>3 checks each</span><span>60 seconds</span>
            </div>
            {vm.error && <p className="game-error">{vm.error}</p>}
            <button className="game-primary-button" onClick={() => void vm.start()} disabled={vm.isBusy || agents.length === 0}>
              <Play size={18} /> {vm.isBusy ? 'Starting...' : 'Start game'}
            </button>
          </div>
        </section>
      </main>
    )
  }

  if (vm.state.completed && round) {
    const resultTitle = vm.state.overall_winner === 'user' ? 'You won!' : vm.state.overall_winner === 'agent' ? `${vm.state.agent_name} won` : 'Draw game'
    return (
      <main className="graph-game summary">
        <header className="graph-game-header"><div><span className="game-eyebrow">Match complete</span><h1>Graph Match</h1></div></header>
        <section className="game-summary-content">
          <Trophy size={44} />
          <h2>{resultTitle}</h2>
          <div className="final-score"><strong>{vm.state.user_round_wins}</strong><span>You · {vm.state.agent_name}</span><strong>{vm.state.agent_round_wins}</strong></div>
          <div className="summary-formulas">
            <span>Final target <MathFormula latex={round.target_latex ?? ''} /></span>
            <span>Your best <MathFormula latex={round.attempts.at(-1)?.latex ?? ''} /></span>
          </div>
          <div className="summary-actions">
            <button className="game-secondary-button" onClick={onExit}><ArrowLeft size={17} /> Study hub</button>
            <button className="game-primary-button" onClick={vm.restart}><RotateCcw size={17} /> Play again</button>
          </div>
        </section>
      </main>
    )
  }

  if (!round) return null

  return (
    <main className="graph-game playing">
      <header className="graph-game-header compact">
        <button className="icon-button" onClick={onExit} aria-label="Exit game" title="Exit game"><ArrowLeft /></button>
        <div><span className="game-eyebrow">Graph Match</span><h1>Round {round.number} of {vm.state.round_count}</h1></div>
        <div className="game-status"><span>You {vm.state.user_round_wins}</span><span>{vm.state.agent_name} {vm.state.agent_round_wins}</span><span className={vm.remainingSeconds <= 10 ? 'timer urgent' : 'timer'}><Clock3 size={16} /> {vm.remainingSeconds}s</span></div>
      </header>

      <section className="graph-game-workspace">
        <div className="graph-stage">
          <div className="graph-legend"><span className="target">Target</span><span className="player">Your graph</span>{round.completed && <span className="agent">{vm.state.agent_name}</span>}</div>
          <FunctionGraph target={round.target_points} player={vm.playerPoints} agent={round.agent_points} />
        </div>

        <aside className="function-controls">
          <div className="live-formula"><MathFormula latex={vm.formula} block /></div>

          <div className="control-group">
            <span className="control-label">Direction</span>
            <div className="segmented-control">
              <button className={vm.input.coefficient === 1 ? 'active' : ''} onClick={() => vm.updateInput({ coefficient: 1 })}>Up</button>
              <button className={vm.input.coefficient === -1 ? 'active' : ''} onClick={() => vm.updateInput({ coefficient: -1 })}>Reflected</button>
            </div>
          </div>

          <div className="control-group">
            <span className="control-label">Base</span>
            <div className="base-options">
              {baseOptions.map(base => (
                <button key={base} className={vm.input.base === base ? 'active' : ''} onClick={() => vm.updateInput({ base })}>
                  <MathFormula latex={base === 1 / 3 ? '\\frac{1}{3}' : base === 1 / 2 ? '\\frac{1}{2}' : String(base)} />
                </button>
              ))}
            </div>
          </div>

          <Stepper label="Horizontal shift" symbol="h" value={vm.input.horizontal_shift} onChange={value => vm.updateInput({ horizontal_shift: value })} />
          <Stepper label="Vertical shift" symbol="k" value={vm.input.vertical_shift} onChange={value => vm.updateInput({ vertical_shift: value })} />

          {round.attempts.length > 0 && <div className="attempt-history">{round.attempts.map((attempt, index) => <span key={`${attempt.latex}-${index}`}><MathFormula latex={attempt.latex} /><strong>{attempt.score}</strong></span>)}</div>}
          {vm.error && <p className="game-error">{vm.error}</p>}

          {!round.completed ? (
            <button className="game-primary-button" onClick={() => void vm.submit()} disabled={vm.isBusy}>
              <Send size={17} /> {vm.remainingSeconds === 0 ? 'Time is up · Submit' : `Check graph · ${round.attempts_remaining} left`}
            </button>
          ) : (
            <div className="round-result">
              <span className={`round-winner ${round.winner}`}>{round.winner === 'user' ? 'You win this round' : round.winner === 'agent' ? `${vm.state.agent_name} wins this round` : 'Round draw'}</span>
              <div><span>Target <MathFormula latex={round.target_latex ?? ''} /></span><span>{vm.state.agent_name} <MathFormula latex={round.agent_latex ?? ''} /> · {round.agent_score}</span></div>
              <button className="game-primary-button" onClick={() => void vm.advance()} disabled={vm.isBusy}>Next round <ChevronRight size={18} /></button>
            </div>
          )}
        </aside>
      </section>

      <footer className="quick-chat-bar">
        <div className="quick-chat-log">{vm.state.quick_chats.slice(-2).map((event, index) => <span key={`${event.sender}-${index}`} className={event.sender}>{event.sender === 'agent' ? vm.state?.agent_name : 'You'}: {event.text}</span>)}</div>
        <div className="quick-chat-actions">{quickChats.map(([id, text]) => <button key={id} onClick={() => void vm.quickChat(id)} disabled={vm.isBusy}>{text}</button>)}</div>
      </footer>
    </main>
  )
}

function Stepper({ label, symbol, value, onChange }: { label: string; symbol: string; value: number; onChange: (value: number) => void }) {
  return (
    <div className="control-group stepper-group">
      <span className="control-label">{label} <MathFormula latex={symbol} /></span>
      <div className="number-stepper">
        <button onClick={() => onChange(Math.max(-2, value - 1))} disabled={value <= -2} aria-label={`Decrease ${label}`} title={`Decrease ${label}`}><Minus size={16} /></button>
        <strong>{value}</strong>
        <button onClick={() => onChange(Math.min(2, value + 1))} disabled={value >= 2} aria-label={`Increase ${label}`} title={`Increase ${label}`}><Plus size={16} /></button>
      </div>
    </div>
  )
}
