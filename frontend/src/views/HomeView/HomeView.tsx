import { BookOpen, Bot, BrainCircuit, MessageCircle, Plus, Trash2, X } from 'lucide-react'
import type { HomeViewModel } from './useHomeViewModel'

interface HomeViewProps {
  vm: HomeViewModel
}

export default function HomeView({ vm }: HomeViewProps) {
  return (
    <main className="home-view">
      <section className="home-panel">
        <div className="home-heading">
          <span className="home-kicker">AI HomeSchooling</span>
          <h1>Study hub</h1>
          <p>Choose where to start.</p>
        </div>

        <div className="home-actions" aria-label="Main actions">
          <button className="home-action primary" onClick={vm.openLesson}>
            <BookOpen size={22} />
            <span>
              <strong>Enter class</strong>
              <small>{vm.primaryLecture.title}</small>
            </span>
          </button>

          <button className="home-action" onClick={vm.openProblemSolving}>
            <BrainCircuit size={22} />
            <span>
              <strong>Practice problems</strong>
              <small>Work through examples with Isabella</small>
            </span>
          </button>

          <button className="home-action" onClick={vm.openCreateAgent}>
            <Plus size={22} />
            <span>
              <strong>Add Agent</strong>
              <small>Design a new conversation friend</small>
            </span>
          </button>
        </div>
      </section>

      <section className="home-panel agent-panel">
        <div className="home-section-title">
          <Bot size={18} />
          <span>Agents</span>
        </div>

        <div className="home-agent-list">
          {vm.isLoadingAgents && <div className="home-agent-status">Refreshing Agents...</div>}
          {vm.agentLoadError && <div className="home-agent-status error">{vm.agentLoadError}</div>}
          {vm.agents.map(agent => (
            <div key={agent.id} className="home-agent-item">
              <div className="home-agent-item-main">
                <button
                  className="home-agent-row"
                  onClick={() => vm.openAgent(agent.id)}
                >
                  <span className="home-agent-avatar">
                    {agent.avatarByMood?.happy ? (
                      <img src={agent.avatarByMood.happy} alt="" />
                    ) : (
                      <MessageCircle size={20} />
                    )}
                  </span>
                  <span className="home-agent-copy">
                    <strong>{agent.entryLabel}</strong>
                    <small>{agent.description}</small>
                  </span>
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
                  <button
                    onClick={vm.cancelDeleteAgent}
                    aria-label="Cancel deletion"
                    title="Cancel deletion"
                  >
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
    </main>
  )
}
