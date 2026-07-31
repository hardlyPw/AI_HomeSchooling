import { BookOpen, Bot, BrainCircuit, MessageCircle, Plus } from 'lucide-react'
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

          <button className="home-action disabled" disabled>
            <Plus size={22} />
            <span>
              <strong>Add Agent</strong>
              <small>Coming after agent abstraction</small>
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
          {vm.agents.map(agent => (
            <button
              key={agent.id}
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
          ))}
        </div>
      </section>
    </main>
  )
}
