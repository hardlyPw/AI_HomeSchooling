import { useCallback, useState } from 'react'
import { gameClient, type GameId, type LeaderboardEntry } from '../../clients/games/GameClient'

export type GameHubSection = 'games' | 'history'
export type ActiveGame = 'graph' | 'memory' | null

export const useGameHubViewModel = () => {
  const [section, setSection] = useState<GameHubSection>('games')
  const [activeGame, setActiveGame] = useState<ActiveGame>(null)
  const [historyGame, setHistoryGame] = useState<GameId>('graph_challenge')
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [error, setError] = useState('')

  const loadHistory = useCallback(async (gameId: GameId) => {
    setIsLoadingHistory(true)
    setError('')
    try {
      const response = await gameClient.leaderboard(gameId)
      setEntries(response.entries)
    } catch (requestError) {
      setEntries([])
      setError(requestError instanceof Error ? requestError.message : 'Could not load game history.')
    } finally {
      setIsLoadingHistory(false)
    }
  }, [])

  return {
    section,
    activeGame,
    historyGame,
    entries,
    isLoadingHistory,
    error,
    showGames: () => { setSection('games'); setActiveGame(null) },
    showHistory: () => { setSection('history'); setActiveGame(null); void loadHistory(historyGame) },
    openGraph: () => setActiveGame('graph'),
    openMemory: () => setActiveGame('memory'),
    closeGame: () => setActiveGame(null),
    setHistoryGame: (gameId: GameId) => { setHistoryGame(gameId); void loadHistory(gameId) },
  }
}
