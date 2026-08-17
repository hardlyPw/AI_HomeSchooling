import { BrainCircuit, Gamepad2, MessageCircle, Plus, Trash2, X } from 'lucide-react'
import type { HomeViewModel } from './useHomeViewModel'

interface HomeViewProps {
  vm: HomeViewModel
}

export default function HomeView({ vm }: HomeViewProps) {
  return (
    <main className="home-view">
      <header className="home-app-header">
        <div>
          <span>Personal learning space</span>
          <strong>AI HomeSchooling</strong>
        </div>
      </header>

      <div className="home-content">
        <section className="home-main-column">
          <div className="home-heading">
            <span className="home-kicker">Study hub</span>
            <h1>Good afternoon</h1>
            <p>Continue your class or catch up with a friend.</p>
          </div>

          <section className="home-continue-card">
            <div>
              <span>Continue class</span>
              <h2>{vm.primaryLecture.title}</h2>
              <p>Pick up where you left off.</p>
              <button onClick={vm.openLesson}>Continue</button>
            </div>
            <img src="/assets/classroom_bg.png" alt="" />
          </section>

          <div className="home-actions" aria-label="Main actions">
            <button className="home-action" onClick={vm.openProblemSolving}>
              <BrainCircuit size={20} />
              <span>
                <strong>Practice problems</strong>
                <small>Solve questions with Isabella</small>
              </span>
            </button>

            <button className="home-action" onClick={vm.openGame}>
              <Gamepad2 size={20} />
              <span>
                <strong>Play a game</strong>
                <small>Solo challenges and friend matches</small>
              </span>
            </button>

            <button className="home-action" onClick={vm.openCreateAgent}>
              <Plus size={20} />
              <span>
                <strong>Add a friend</strong>
                <small>Meet someone new to learn with</small>
              </span>
            </button>
          </div>
        </section>

        <section className="home-friends-panel">
          <div className="home-section-title">
            <span>Friends</span>
            <button onClick={vm.openCreateAgent} aria-label="Add a friend" title="Add a friend">
              <Plus size={17} />
            </button>
          </div>

          <div className="home-agent-list">
            {vm.isLoadingAgents && <div className="home-agent-status">Refreshing friends...</div>}
            {vm.agentLoadError && <div className="home-agent-status error">{vm.agentLoadError}</div>}
            {vm.agents.map(agent => (
              <div key={agent.id} className="home-agent-item">
                <div className="home-agent-item-main">
                  <button className="home-agent-row" onClick={() => vm.openAgent(agent.id)}>
                    <span className="home-agent-avatar">
                      {agent.avatarByMood?.happy ? (
                        <img src={agent.avatarByMood.happy} alt="" />
                      ) : (
                        <MessageCircle size={20} />
                      )}
                      <i className={agent.isOnline ? 'online' : 'offline'} aria-label={agent.isOnline ? 'Online' : 'Offline'} />
                    </span>
                    <span className="home-agent-copy">
                      <strong>{agent.name}</strong>
                    </span>
                    <span className="home-agent-message">Message</span>
                  </button>
                  {!agent.isBuiltin && (
                    <button
                      className="home-agent-delete"
                      onClick={() => vm.requestDeleteAgent(agent.id)}
                      aria-label={`Delete ${agent.name}`}
                      title={`Delete ${agent.name}`}
                    >
                      <Trash2 size={17} />
                    </button>
                  )}
                </div>
                {vm.pendingDeleteId === agent.id && (
                  <div className="home-agent-delete-confirm">
                    <span>Delete {agent.name}?</span>
                    <button onClick={vm.cancelDeleteAgent} aria-label="Cancel deletion" title="Cancel deletion">
                      <X size={16} />
                    </button>
                    <button
                      className="danger"
                      onClick={() => void vm.confirmDeleteAgent()}
                      disabled={vm.deletingAgentId === agent.id}
                    >
                      {vm.deletingAgentId === agent.id ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
