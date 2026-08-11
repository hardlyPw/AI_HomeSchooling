import { ArrowLeft, Brain, ChevronRight, FunctionSquare, Gamepad2, History as HistoryIcon, Medal, Trophy } from 'lucide-react'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import GraphChallengeView from './GraphChallengeView'
import MemoryMatchView from './MemoryMatchView'
import { useGameHubViewModel } from './useGameHubViewModel'

interface GameHubViewProps {
  agents: AgentProfile[]
  onExit: () => void
}

const historyDateFormatter = new Intl.DateTimeFormat('en', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

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
          <button className={vm.section === 'history' ? 'active' : ''} onClick={vm.showHistory} role="tab"><HistoryIcon size={17} /> History</button>
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
              <span><small>Agent duel</small><strong>Memory Match</strong><p>Memorize 36 cards, find number pairs, and earn extra turns.</p><em>15s preview · 15s turns · Quick chat</em></span>
              <ChevronRight />
            </button>
          </div>
        </section>
      ) : (
        <section className="leaderboard-view">
          <div className="leaderboard-tabs" role="tablist">
            <button className={vm.historyGame === 'graph_challenge' ? 'active' : ''} onClick={() => vm.setHistoryGame('graph_challenge')} role="tab">Graph Challenge</button>
            <button className={vm.historyGame === 'memory_match' ? 'active' : ''} onClick={() => vm.setHistoryGame('memory_match')} role="tab">Memory Match</button>
          </div>
          <div className="leaderboard-content">
            <div className="leaderboard-title"><Medal size={25} /><div><h2>{vm.historyGame === 'graph_challenge' ? 'Graph Challenge ranking' : 'Memory Match history'}</h2><p>{vm.historyGame === 'graph_challenge' ? 'Highest three-round scores' : 'Latest matches against Agents'}</p></div></div>
            {vm.isLoadingHistory && <div className="leaderboard-empty">Loading history...</div>}
            {vm.error && <div className="leaderboard-empty error">{vm.error}</div>}
            {!vm.isLoadingHistory && !vm.error && vm.entries.length === 0 && <div className="leaderboard-empty"><Trophy size={34} /><strong>No history yet</strong><span>Complete a game to create your first record.</span></div>}
            {vm.entries.length > 0 && vm.historyGame === 'graph_challenge' && <RankingTable entries={vm.entries} />}
            {vm.entries.length > 0 && vm.historyGame === 'memory_match' && <MatchHistoryTable entries={vm.entries} />}
          </div>
        </section>
      )}
    </main>
  )
}

function RankingTable({ entries }: { entries: ReturnType<typeof useGameHubViewModel>['entries'] }) {
  return (
    <div className="leaderboard-table" role="table" aria-label="Graph Challenge ranking">
      <div className="leaderboard-row heading" role="row"><span>Rank</span><span>Player</span><span>Result</span><span>Score</span></div>
      {entries.map(entry => <div key={`${entry.rank}-${entry.played_at}`} className={`leaderboard-row rank-${entry.rank}`} role="row"><b>{entry.rank}</b><strong>{entry.player_name}</strong><span>{entry.detail}</span><em>{entry.score}</em></div>)}
    </div>
  )
}

function MatchHistoryTable({ entries }: { entries: ReturnType<typeof useGameHubViewModel>['entries'] }) {
  return (
    <div className="leaderboard-table match-history-table" role="table" aria-label="Memory Match history">
      <div className="leaderboard-row heading" role="row"><span>Played</span><span>Player</span><span>Match</span><span>Pairs</span></div>
      {entries.map(entry => (
        <div key={`${entry.rank}-${entry.played_at}`} className="leaderboard-row" role="row">
          <time dateTime={entry.played_at}>{historyDateFormatter.format(new Date(entry.played_at))}</time>
          <strong>{entry.player_name}</strong>
          <span>{entry.detail}</span>
          <em>{entry.score}</em>
        </div>
      ))}
    </div>
  )
}
