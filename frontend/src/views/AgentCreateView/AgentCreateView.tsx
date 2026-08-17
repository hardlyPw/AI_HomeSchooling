import { ArrowLeft, Sparkles } from 'lucide-react'
import type {
  AgentCreateField,
  AgentCreateViewModel,
} from './useAgentCreateViewModel'

interface AgentCreateViewProps {
  vm: AgentCreateViewModel
}

interface TextFieldProps {
  field: AgentCreateField
  label: string
  value: string
  placeholder: string
  multiline?: boolean
  required?: boolean
  onChange: (field: AgentCreateField, value: string) => void
}

function TextField({
  field,
  label,
  value,
  placeholder,
  multiline = false,
  required = false,
  onChange,
}: TextFieldProps) {
  return (
    <label className="agent-create-field">
      <span>{label}{required && <strong>Required</strong>}</span>
      {multiline ? (
        <textarea
          value={value}
          placeholder={placeholder}
          onChange={event => onChange(field, event.target.value)}
        />
      ) : (
        <input
          value={value}
          placeholder={placeholder}
          onChange={event => onChange(field, event.target.value)}
        />
      )}
    </label>
  )
}

export default function AgentCreateView({ vm }: AgentCreateViewProps) {
  return (
    <main className="agent-create-view">
      <header className="agent-create-header">
        <button onClick={vm.cancel} aria-label="Back to home" title="Back to home">
          <ArrowLeft size={19} />
        </button>
        <div>
          <span>New friend</span>
          <h1>Design a friend</h1>
        </div>
      </header>

      <form
        className="agent-create-form"
        onSubmit={event => {
          event.preventDefault()
          void vm.submit()
        }}
      >
        <section className="agent-create-section">
          <h2>Identity</h2>
          <div className="agent-create-grid">
            <TextField field="requested_name" label="Name" value={vm.form.requested_name} placeholder="Mina" required onChange={vm.setField} />
            <label className="agent-create-field">
              <span>Relationship<strong>Required</strong></span>
              <select value={vm.form.relationship} onChange={event => vm.setField('relationship', event.target.value)}>
                <option>A same-age classmate who already knows me a little.</option>
                <option>A longtime neighborhood friend who knows me well.</option>
                <option>An online friend I met through shared interests.</option>
                <option>A new friend who is still getting to know me.</option>
              </select>
            </label>
          </div>
          <TextField field="background" label="Background" value={vm.form.background} placeholder="Family, school life, daily routine, or a short backstory." multiline onChange={vm.setField} />
        </section>

        <section className="agent-create-section">
          <h2>Personality and voice</h2>
          <TextField field="personality" label="What are they like?" value={vm.form.personality} placeholder="Direct but caring, playful, independent, and honest when something feels off." multiline required onChange={vm.setField} />
          <label className="agent-create-field">
            <span>Texting style<strong>Required</strong></span>
            <select value={vm.form.speech_style} onChange={event => vm.setField('speech_style', event.target.value)}>
              <option>Short, casual messages with natural slang in moderation.</option>
              <option>Warm and expressive messages with playful reactions.</option>
              <option>Calm, thoughtful messages with a little more detail.</option>
              <option>Dry, concise messages with understated humor.</option>
            </select>
          </label>
          <TextField field="reaction_style" label="How should they react?" value={vm.form.reaction_style} placeholder="How they handle good news, complaints, conflict, compliments, or serious moments." multiline onChange={vm.setField} />
        </section>

        <section className="agent-create-section">
          <h2>Interests and boundaries</h2>
          <TextField field="interests" label="Interests" value={vm.form.interests} placeholder="Drawing, indie music, basketball, games, cooking..." required onChange={vm.setField} />
          <TextField field="avoidances" label="Things to avoid" value={vm.form.avoidances} placeholder="Overpraising, lecturing, too many questions, specific slang, or unwanted topics." multiline onChange={vm.setField} />
          <TextField field="dialogue_examples" label="Example messages" value={vm.form.dialogue_examples} placeholder={'User: i finally finished it\nFriend: took you long enough lol. how bad was it'} multiline onChange={vm.setField} />
          <TextField field="additional_description" label="Anything else" value={vm.form.additional_description} placeholder="Add any detail that did not fit above." multiline onChange={vm.setField} />
        </section>

        {vm.error && <div className="agent-create-error">{vm.error}</div>}

        <footer className="agent-create-footer">
          <button type="button" className="secondary" onClick={vm.cancel} disabled={vm.isSubmitting}>Cancel</button>
          <button type="submit" className="primary" disabled={!vm.canSubmit || vm.isSubmitting}>
            <Sparkles size={17} />
            {vm.isSubmitting ? 'Designing...' : 'Create friend'}
          </button>
        </footer>
      </form>
    </main>
  )
}
