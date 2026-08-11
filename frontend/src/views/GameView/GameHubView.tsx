import { ArrowLeft, Brain, ChevronRight, FunctionSquare, Gamepad2, Medal, Trophy } from 'lucide-react'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import GraphChallengeView from './GraphChallengeView'
import MemoryMatchView from './MemoryMatchView'
import { useGameHubViewModel } from './useGameHubViewModel'

interface GameHubViewProps {
  agents: AgentProfile[]
  onExit: () => void
}

export default function GameHubView({ agents, onExit }: GameHubViewProps) {
  const vm = useGameHubViewModel()
  if (vm.activeGame === 'graph') return <GraphChallengeView onExit={vm.closeGame} />
  if (vm.activeGame === 'memory') return <MemoryMatchView agents={agents} onExit={vm.closeGame} />

  return (
    <main className="game-hub">
      <header className="game-hub-header">
        <button className="icon-button" onClick={onExit} aria-label="Back to study hub" title="Back to study hub"><ArrowLeft /></button>
        <div><span className="game-eyebrow">AI HomeSchooling</span><h1>Game room</h1></div>
        <div className="game-hub-mode" role="tablist">
          <button className={vm.section === 'games' ? 'active' : ''} onClick={vm.showGames} role="tab"><Gamepad2 size={17} /> Games</button>
          <button className={vm.section === 'rankings' ? 'active' : ''} onClick={vm.showRankings} role="tab"><Trophy size={17} /> Rankings</button>
        </div>
      </header>

      {vm.section === 'games' ? (
        <section className="game-catalog">
          <div className="game-catalog-heading"><h2>Choose a game</h2><p>Practice on your own or challenge an Agent.</p></div>
          <div className="game-catalog-list">
            <button className="game-catalog-item graph" onClick={vm.openGraph}>
              <span className="game-catalog-icon"><FunctionSquare size={32} /></span>
              <span><small>Solo · Ranked</small><strong>Graph Challenge</strong><p>Build functions from interactive graphs using a scientific keypad.</p><em>Linear · Polynomial · Exponential · Log · Trig</em></span>
              <ChevronRight />
            </button>
            <button className="game-catalog-item memory" onClick={vm.openMemory}>
              <span className="game-catalog-icon"><Brain size={32} /></span>
              <span><small>Agent duel</small><strong>Memory Match</strong><p>Memorize 36 cards, find number pairs, and earn extra turns.</p><em>10s preview · 15s turns · Quick chat</em></span>
              <ChevronRight />
            </button>
          </div>
        </section>
      ) : (
        <section className="leaderboard-view">
          <div className="leaderboard-tabs" role="tablist">
            <button className={vm.rankingGame === 'graph_challenge' ? 'active' : ''} onClick={() => vm.setRankingGame('graph_challenge')} role="tab">Graph Challenge</button>
            <button className={vm.rankingGame === 'memory_match' ? 'active' : ''} onClick={() => vm.setRankingGame('memory_match')} role="tab">Memory Match</button>
          </div>
          <div className="leaderboard-content">
            <div className="leaderboard-title"><Medal size={25} /><div><h2>{vm.rankingGame === 'graph_challenge' ? 'Graph Challenge' : 'Memory Match'} ranking</h2><p>{vm.rankingGame === 'graph_challenge' ? 'Highest three-round score' : 'Most pairs found in one match'}</p></div></div>
            {vm.isLoadingRankings && <div className="leaderboard-empty">Loading ranking...</div>}
            {vm.error && <div className="leaderboard-empty error">{vm.error}</div>}
            {!vm.isLoadingRankings && !vm.error && vm.entries.length === 0 && <div className="leaderboard-empty"><Trophy size={34} /><strong>No scores yet</strong><span>Complete a game to take the first place.</span></div>}
            {vm.entries.length > 0 && (
              <div className="leaderboard-table" role="table" aria-label="Game ranking">
                <div className="leaderboard-row heading" role="row"><span>Rank</span><span>Player</span><span>Result</span><span>Score</span></div>
                {vm.entries.map(entry => <div key={`${entry.rank}-${entry.played_at}`} className={`leaderboard-row rank-${entry.rank}`} role="row"><b>{entry.rank}</b><strong>{entry.player_name}</strong><span>{entry.detail}</span><em>{entry.score}</em></div>)}
              </div>
            )}
          </div>
        </section>
      )}
    </main>
  )
}
