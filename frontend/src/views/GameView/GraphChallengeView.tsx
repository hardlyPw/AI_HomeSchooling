import { ArrowLeft, ChevronRight, Clock3, MousePointer2, Play, RotateCcw, Trophy } from 'lucide-react'
import ExpressionKeypad from './ExpressionKeypad'
import FunctionGraph from './FunctionGraph'
import MathFormula from './MathFormula'
import { useGraphChallengeViewModel } from './useGraphChallengeViewModel'

interface GraphChallengeViewProps {
  onExit: () => void
}

export default function GraphChallengeView({ onExit }: GraphChallengeViewProps) {
  const vm = useGraphChallengeViewModel()
  const round = vm.state?.current_round

  if (!vm.state) {
    return (
      <main className="graph-game solo-lobby">
        <header className="graph-game-header">
          <button className="icon-button" onClick={onExit} aria-label="Back" title="Back"><ArrowLeft /></button>
          <div><span className="game-eyebrow">Solo score challenge</span><h1>Graph Challenge</h1></div>
        </header>
        <section className="solo-graph-intro">
          <div className="solo-graph-preview" aria-hidden="true"><span /><span /><span /></div>
          <div className="solo-graph-copy">
            <h2>Read the graph. Build the function.</h2>
            <p>Three rounds can include linear, polynomial, exponential, logarithmic, and trigonometric functions.</p>
            <div className="game-rule-strip"><span>3 rounds</span><span>1 submission</span><span>60 seconds</span><span>Ranked score</span></div>
            {vm.error && <p className="game-error">{vm.error}</p>}
            <button className="game-primary-button" onClick={() => void vm.start()} disabled={vm.isBusy}><Play size={18} /> {vm.isBusy ? 'Starting...' : 'Start solo run'}</button>
          </div>
        </section>
      </main>
    )
  }

  if (vm.state.completed) {
    return (
      <main className="graph-game summary solo-summary">
        <header className="graph-game-header"><div><span className="game-eyebrow">Run complete</span><h1>Graph Challenge</h1></div></header>
        <section className="game-summary-content">
          <Trophy size={42} />
          <h2>{vm.state.total_score} points</h2>
          <div className="solo-round-summary">
            {vm.state.rounds.map(result => (
              <article key={result.number}>
                <span>Round {result.number} · {result.family}</span>
                <MathFormula latex={result.target_latex ?? ''} />
                <strong>{result.attempt?.score ?? 0}</strong>
                <small>{result.attempt?.graph_score ?? 0} graph + {result.attempt?.time_bonus ?? 0} time</small>
              </article>
            ))}
          </div>
          <div className="summary-actions">
            <button className="game-secondary-button" onClick={onExit}><ArrowLeft size={17} /> Games</button>
            <button className="game-primary-button" onClick={vm.restart}><RotateCcw size={17} /> Play again</button>
          </div>
        </section>
      </main>
    )
  }

  if (!round) return null
  return (
    <main className="graph-game playing solo-playing">
      <header className="graph-game-header compact">
        <button className="icon-button" onClick={onExit} aria-label="Exit game" title="Exit game"><ArrowLeft /></button>
        <div><span className="game-eyebrow">{round.family}</span><h1>Round {round.number} of {vm.state.round_count}</h1></div>
        <div className="solo-game-status"><strong>{vm.state.total_score} pts</strong><span className={vm.remainingSeconds <= 10 ? 'timer urgent' : 'timer'}><Clock3 size={16} /> {vm.remainingSeconds}s</span></div>
      </header>
      <section className="graph-game-workspace solo">
        <div className="graph-stage">
          <div className="graph-legend"><span className="target">Target</span><span className="player">Your function</span></div>
          <FunctionGraph target={round.target_points} player={vm.playerPoints} />
          <div className="graph-navigation-hint"><MousePointer2 size={15} /> Drag to move · Scroll to zoom</div>
        </div>
        <aside className="function-controls calculator-panel">
          <ExpressionKeypad value={vm.expression} onChange={vm.setExpression} onSubmit={() => void vm.submit()} disabled={vm.isBusy || round.completed} />
          {vm.error && <p className="game-error">{vm.error}</p>}
          {round.completed && round.attempt && (
            <div className="solo-round-result">
              <span>Target</span><MathFormula latex={round.target_latex ?? ''} block />
              <div><strong>{round.attempt.score}</strong><small>{round.attempt.graph_score} graph + {round.attempt.time_bonus} time</small></div>
              <button className="game-primary-button" onClick={() => void vm.advance()} disabled={vm.isBusy}>Next round <ChevronRight size={18} /></button>
            </div>
          )}
        </aside>
      </section>
    </main>
  )
}
