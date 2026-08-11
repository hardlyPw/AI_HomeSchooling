import { useCallback, useState } from 'react'
import { gameClient, type GameId, type LeaderboardEntry } from '../../clients/games/GameClient'

export type GameHubSection = 'games' | 'rankings'
export type ActiveGame = 'graph' | 'memory' | null

export const useGameHubViewModel = () => {
  const [section, setSection] = useState<GameHubSection>('games')
  const [activeGame, setActiveGame] = useState<ActiveGame>(null)
  const [rankingGame, setRankingGame] = useState<GameId>('graph_challenge')
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [isLoadingRankings, setIsLoadingRankings] = useState(false)
  const [error, setError] = useState('')

  const loadRankings = useCallback(async (gameId: GameId) => {
    setIsLoadingRankings(true)
    setError('')
    try {
      const response = await gameClient.leaderboard(gameId)
      setEntries(response.entries)
    } catch (requestError) {
      setEntries([])
      setError(requestError instanceof Error ? requestError.message : 'Could not load the leaderboard.')
    } finally {
      setIsLoadingRankings(false)
    }
  }, [])

  return {
    section,
    activeGame,
    rankingGame,
    entries,
    isLoadingRankings,
    error,
    showGames: () => { setSection('games'); setActiveGame(null) },
    showRankings: () => { setSection('rankings'); setActiveGame(null); void loadRankings(rankingGame) },
    openGraph: () => setActiveGame('graph'),
    openMemory: () => setActiveGame('memory'),
    closeGame: () => setActiveGame(null),
    setRankingGame: (gameId: GameId) => { setRankingGame(gameId); void loadRankings(gameId) },
  }
}
