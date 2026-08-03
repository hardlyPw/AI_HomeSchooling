import { useMemo, useState } from 'react'
import {
  agentCatalogClient,
  type CreateAgentRequest,
} from '../../clients/agents/AgentCatalogClient'
import type { AgentProfile } from '../../domain/agents/AgentProfile'
import { upsertAgentProfiles } from '../../domain/agents/agentRegistry'

export type AgentCreateField = keyof CreateAgentRequest

const INITIAL_FORM: CreateAgentRequest = {
  requested_name: '',
  relationship: 'A same-age classmate who already knows me a little.',
  personality: '',
  speech_style: 'Short, casual messages with natural slang in moderation.',
  interests: '',
  reaction_style: '',
  background: '',
  avoidances: '',
  dialogue_examples: '',
  additional_description: '',
}

interface UseAgentCreateViewModelParams {
  onCancel: () => void
  onCreated: (agent: AgentProfile) => void
}

export interface AgentCreateViewModel {
  form: CreateAgentRequest
  isSubmitting: boolean
  error: string
  canSubmit: boolean
  setField: (field: AgentCreateField, value: string) => void
  submit: () => Promise<void>
  cancel: () => void
}

export const useAgentCreateViewModel = ({
  onCancel,
  onCreated,
}: UseAgentCreateViewModelParams): AgentCreateViewModel => {
  const [form, setForm] = useState(INITIAL_FORM)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const canSubmit = useMemo(
    () => Boolean(
      form.requested_name.trim()
      && form.relationship.trim()
      && form.personality.trim()
      && form.speech_style.trim()
      && form.interests.trim()
    ),
    [form],
  )

  const setField = (field: AgentCreateField, value: string) => {
    setForm(current => ({ ...current, [field]: value }))
  }

  const submit = async () => {
    if (!canSubmit || isSubmitting) return
    setIsSubmitting(true)
    setError('')
    try {
      const agent = await agentCatalogClient.createAgent(form)
      upsertAgentProfiles([agent])
      onCreated(agent)
    } catch (requestError) {
      console.error(requestError)
      setError('Could not create this Agent. Check the backend connection and try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return {
    form,
    isSubmitting,
    error,
    canSubmit,
    setField,
    submit,
    cancel: onCancel,
  }
}
