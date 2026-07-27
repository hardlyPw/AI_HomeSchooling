import { useState } from 'react'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import AppShell from './app/AppShell'
import type { AppMode } from './types'
import { useHomeViewModel } from './views/HomeView/useHomeViewModel'
import { useLearningViewModel } from './views/LearningView/useLearningViewModel'
import './App.css'

function App() {
  const [appMode, setAppMode] = useState<AppMode>('home')
  const [selectedAgentId, setSelectedAgentId] = useState('jiho')

  const learningVm = useLearningViewModel({
    navigateHome: () => setAppMode('home'),
    navigateLesson: () => setAppMode('lesson'),
    navigatePlaylist: () => setAppMode('playlist'),
  })

  const homeVm = useHomeViewModel({
    onOpenAgent: agentId => {
      setSelectedAgentId(agentId)
      setAppMode('agent-chat')
    },
    onOpenLesson: learningVm.openLecture,
    onOpenProblemSolving: learningVm.enterAutoraterMode,
  })

  return (
    <AppShell
      currentView={appMode}
      homeVm={homeVm}
      selectedAgentId={selectedAgentId}
      selectedLectureId={learningVm.selectedLectureId}
      lectureThumbnails={learningVm.lectureThumbnails}
      renderLessonView={learningVm.renderLessonView}
      openHome={learningVm.goHome}
      openPlaylist={learningVm.openPlaylist}
      openLecture={learningVm.openLecture}
    />
  )
}

export default App
