import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import LessonStage from '../../components/LessonStage'
import PdfPanel from '../../components/PdfPanel'
import QuickActions from '../../components/QuickActions'
import StudyChatPanel from '../../components/StudyChatPanel'
import { LECTURES } from '../../constants'
import PracticeIntroView from './PracticeIntroView'
import PracticeSummaryView from './PracticeSummaryView'
import { useAutoraterViewModel } from './hooks/useAutoraterViewModel'
import { useLectureViewModel } from './hooks/useLectureViewModel'
import { useLessonChatViewModel } from './hooks/useLessonChatViewModel'
import { usePdfSelectionViewModel } from './hooks/usePdfSelectionViewModel'

interface UseLearningViewModelParams {
  navigateHome: () => void
  navigateLesson: () => void
  navigatePlaylist: () => void
}

export interface LearningViewModel {
  selectedLectureId: string
  lectureThumbnails: Record<string, string>
  renderLessonView: () => ReactNode
  goHome: () => void
  openPlaylist: () => void
  openLecture: (lectureId?: string) => void
  enterAutoraterMode: () => void
}

export const useLearningViewModel = ({
  navigateHome,
  navigateLesson,
  navigatePlaylist,
}: UseLearningViewModelParams): LearningViewModel => {
  const [showChat, setShowChat] = useState(false)
  const [showPdf, setShowPdf] = useState(false)
  const [hasOpenedPdf, setHasOpenedPdf] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)

  const lectureVm = useLectureViewModel()
  const lessonChatVm = useLessonChatViewModel()
  const pdfVm = usePdfSelectionViewModel({
    showPdf,
    onContextQueued: () => setShowChat(true),
  })
  const autoraterVm = useAutoraterViewModel({
    clearChatContext: pdfVm.clearChatContext,
    openWorkspace: () => {
      setShowChat(true)
      setHasOpenedPdf(true)
      setShowPdf(true)
      pdfVm.clearPendingPdfSelection()
      pdfVm.setPendingFigureSelection(null)
    },
    closeWorkspace: () => {
      setShowChat(false)
      setShowPdf(false)
    },
  })

  const activeInput = autoraterVm.autoraterMode ? autoraterVm.exampleInput : lessonChatVm.lessonInput
  const activeMessages = autoraterVm.autoraterMode ? autoraterVm.exampleMessages : lessonChatVm.lessonMessages

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [activeMessages, showChat])

  useEffect(() => {
    if (!showChat) return
    const timeout = window.setTimeout(() => chatInputRef.current?.focus(), 100)
    return () => window.clearTimeout(timeout)
  }, [showChat])

  const resetLessonPage = () => {
    lessonChatVm.reset()
    pdfVm.clearChatContext()
    setShowChat(false)
    setShowPdf(false)
    setHasOpenedPdf(false)
    pdfVm.resetScroll()
  }

  const sendMessage = async () => {
    if (autoraterVm.autoraterStarted && autoraterVm.autoraterMode) {
      await autoraterVm.sendAutoraterMessage()
      return
    }

    await lessonChatVm.sendLessonMessage({
      pdfSelections: pdfVm.pdfSelections,
      figureSelections: pdfVm.figureSelections,
      pastedImageSelections: pdfVm.pastedImageSelections,
      attachments: pdfVm.getSelectionAttachments(),
      currentVideoTime: lectureVm.videoRef.current?.currentTime,
      clearContext: pdfVm.clearChatContext,
      ensureChatOpen: () => setShowChat(true),
    })
  }

  const toggleTextbook = () => {
    setHasOpenedPdf(true)
    setShowPdf(prev => !prev)
  }

  const goHome = () => {
    lectureVm.pause()
    lectureVm.setLessonState('paused')
    setShowPdf(false)
    setShowChat(false)
    autoraterVm.resetRuntime()
    navigateHome()
  }

  const enterAutoraterMode = () => {
    lectureVm.pause()
    lectureVm.setLessonState('paused')
    navigateLesson()
    autoraterVm.preparePractice()
  }

  const returnToLesson = () => {
    autoraterVm.resetRuntime()
    setShowChat(false)
    setShowPdf(false)
    setHasOpenedPdf(false)
    navigateLesson()
  }

  const toggleChat = () => {
    setShowChat(prev => !prev)

    const selection = window.getSelection()
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      pdfVm.clearPendingPdfSelection()
    }
  }

  const openPlaylist = () => {
    lectureVm.pause()
    lectureVm.setLessonState('paused')
    setShowPdf(false)
    setShowChat(false)
    navigatePlaylist()
  }

  const openLecture = (lectureId = LECTURES[0].id) => {
    lectureVm.setSelectedLectureId(lectureId)
    autoraterVm.resetRuntime()
    resetLessonPage()
    navigateLesson()
    lectureVm.setLessonState('idle')
  }

  const handleChatInputChange = (value: string) => {
    if (autoraterVm.autoraterMode) {
      autoraterVm.setExampleInput(value)
    } else {
      lessonChatVm.setLessonInput(value)
    }
  }

  const handleChatInputEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    lessonChatVm.handleEnter(e, () => void sendMessage())
  }

  const handleChatPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    void pdfVm.handleChatPaste(e)
  }

  const renderLessonWorkspace = () => (
    <div className={`main-layout${autoraterVm.autoraterMode ? ' autorater-screen' : ''}`}>
      <LessonStage
        selectedLecture={lectureVm.selectedLecture}
        lessonState={lectureVm.lessonState}
        autoraterMode={autoraterVm.autoraterMode}
        videoRef={lectureVm.videoRef}
        onLessonStateChange={lectureVm.setLessonState}
        onOpenPlaylist={openPlaylist}
        onEnterAutoraterMode={enterAutoraterMode}
      />

      {hasOpenedPdf && (
        <PdfPanel
          autoraterMode={autoraterVm.autoraterMode}
          showPdf={showPdf}
          numPages={pdfVm.numPages}
          containerWidth={pdfVm.containerWidth}
          pendingPdfSelection={pdfVm.pendingPdfSelection}
          pendingFigureSelection={pdfVm.pendingFigureSelection}
          selectionButtonAnchor={pdfVm.selectionButtonAnchor}
          pdfPanelRef={pdfVm.pdfPanelRef}
          pdfContainerRef={pdfVm.pdfContainerRef}
          pdfScrollRef={pdfVm.pdfScrollRef}
          onClose={() => setShowPdf(false)}
          onConfirmSelection={pdfVm.confirmSelection}
          onMouseUp={pdfVm.handleMouseUp}
          onPageClick={pdfVm.handlePageClick}
          onScrollTopChange={pdfVm.setScrollTop}
          onDocumentLoad={pdfVm.setNumPages}
        />
      )}

      {showChat && (
        <StudyChatPanel
          autoraterMode={autoraterVm.autoraterMode}
          autoraterStarted={autoraterVm.autoraterStarted}
          autoraterLoading={autoraterVm.autoraterLoading}
          activeInput={activeInput}
          activeMessages={activeMessages}
          pdfSelections={pdfVm.pdfSelections}
          figureSelections={pdfVm.figureSelections}
          pastedImageSelections={pdfVm.pastedImageSelections}
          currentExampleIndex={autoraterVm.currentExampleIndex}
          currentExampleImage={autoraterVm.currentExampleImage}
          currentProblemTotal={autoraterVm.currentProblemTotal}
          totalExamples={autoraterVm.totalExamples}
          completedExamples={autoraterVm.completedExamples}
          exampleComplete={autoraterVm.practicePhase === 'example-complete'}
          isLastExample={autoraterVm.isLastExample}
          exampleImageError={autoraterVm.exampleImageError}
          practiceError={autoraterVm.practiceError}
          scrollRef={scrollRef}
          chatInputRef={chatInputRef}
          onClose={() => setShowChat(false)}
          onContinuePractice={() => void autoraterVm.continuePractice()}
          onEndPractice={returnToLesson}
          onRetryExample={() => void autoraterVm.retryCurrentExample()}
          onExampleImageLoad={() => autoraterVm.setExampleImageError('')}
          onExampleImageError={() => autoraterVm.setExampleImageError('This example image could not be displayed.')}
          onInputChange={handleChatInputChange}
          onInputPaste={handleChatPaste}
          onInputEnter={handleChatInputEnter}
          onSend={() => void sendMessage()}
          onRemovePdfSelection={idx => pdfVm.setPdfSelections(prev => prev.filter((_, i) => i !== idx))}
          onRemoveFigureSelection={idx => pdfVm.setFigureSelections(prev => prev.filter((_, i) => i !== idx))}
          onRemovePastedImageSelection={idx => pdfVm.setPastedImageSelections(prev => prev.filter((_, i) => i !== idx))}
        />
      )}

      {!autoraterVm.autoraterMode && (
        <QuickActions
          showPdf={showPdf}
          showChat={showChat}
          onToggleTextbook={toggleTextbook}
          onToggleChat={toggleChat}
        />
      )}
    </div>
  )

  const renderLessonView = () => {
    if (autoraterVm.practicePhase === 'intro') {
      return (
        <PracticeIntroView
          lecture={lectureVm.selectedLecture}
          totalExamples={autoraterVm.totalExamples}
          isLoading={autoraterVm.autoraterLoading}
          error={autoraterVm.exampleImageError}
          onStart={() => void autoraterVm.beginPractice()}
          onRetry={() => void autoraterVm.loadExamples()}
          onReturnLesson={returnToLesson}
          onReturnHome={goHome}
        />
      )
    }

    if (autoraterVm.practicePhase === 'summary') {
      return (
        <PracticeSummaryView
          lecture={lectureVm.selectedLecture}
          completedExamples={autoraterVm.completedExamples}
          totalExamples={autoraterVm.totalExamples}
          userMessageCount={autoraterVm.userMessageCount}
          elapsedSeconds={autoraterVm.elapsedSeconds}
          onRestart={autoraterVm.preparePractice}
          onReturnLesson={returnToLesson}
          onReturnHome={goHome}
        />
      )
    }

    return renderLessonWorkspace()
  }

  return {
    selectedLectureId: lectureVm.selectedLectureId,
    lectureThumbnails: lectureVm.lectureThumbnails,
    renderLessonView,
    goHome,
    openPlaylist,
    openLecture,
    enterAutoraterMode,
  }
}
