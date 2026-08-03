from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
import json

from domain.agents.conversation import (
    ConversationAgentDefinition,
    ConversationCapability,
)
from infrastructure.storage.namespaced_conversation_memory import (
    ConversationMemoryNamespace,
    NamespacedConversationMemoryStore,
)


class ConfigurableConversationRuntime:
    """Definition-driven runtime shared by user-created conversation Agents."""

    def __init__(
        self,
        *,
        definition: ConversationAgentDefinition,
        user_id: str,
        openai_client,
        memory_store: NamespacedConversationMemoryStore,
    ) -> None:
        self._definition = definition
        self._openai_client = openai_client
        self._memory_store = memory_store
        self._namespace = ConversationMemoryNamespace(
            user_id=user_id,
            agent_id=definition.profile.agent_id,
        )
        self.affinity = definition.profile.initial_affinity
        self.consecutive_negative = 0
        self.conversation_history: list[dict] = []
        self._last_response_usage: dict | None = None

    @property
    def uses_long_term_memory(self) -> bool:
        return (
            self._definition.runtime.memory.enabled
            and ConversationCapability.LONG_TERM_MEMORY
            in self._definition.profile.capabilities
        )

    @property
    def last_response_usage(self) -> dict | None:
        return self._last_response_usage

    def reset_state(self, initial_affinity: int) -> None:
        self.affinity = initial_affinity
        self.consecutive_negative = 0
        self.conversation_history.clear()
        self._last_response_usage = None

    def reset_demo_long_term_memory(self) -> None:
        self._memory_store.clear(self._namespace)

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        if not self.uses_long_term_memory:
            return []
        return self._memory_store.search(self._namespace, query_text, top_k)

    def consume_time_context_for_turn(self) -> tuple[str, str | None]:
        now = datetime.now()
        hour = now.hour
        if 0 <= hour < 6:
            context = "late night"
        elif 6 <= hour < 12:
            context = "morning"
        elif 12 <= hour < 18:
            context = "afternoon"
        else:
            context = "evening"
        return now.strftime("%I:%M %p"), context

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str | None,
    ) -> dict:
        profile = self._definition.profile
        prompt_config = self._definition.runtime.prompt
        recent = self._render_history(prompt_config.decision_history_limit)
        memories = self._render_memories(long_term_memory)
        prompt = f"""You are the behavioral decision layer for {profile.display_name}.
Decide how the character responds, not the final wording.

[Character Guidance]
{profile.persona.decision_guidance}

[Affinity Rubric]
{profile.persona.affinity_rubric}

[Context]
- Time: {time_str} ({time_context or 'unknown'})
- Affinity: {self.affinity}/{profile.affinity_max}

[Recent Chat]
{recent}

[Relevant Memories]
{memories}

[User Message]
{user_message}

Return JSON only:
{{"emotion":"short phrase","emotion_reason":"short phrase","timing":"instant|delayed|double_text|wrap_up","action":"normal|topic_drift|memory_flashback","session_break":false,"affinity_delta":0,"affinity_reason":"short phrase","reasoning":"one sentence"}}
Affinity delta must be between {prompt_config.affinity_delta_min} and {prompt_config.affinity_delta_max}."""
        config = self._definition.runtime.decision_model
        try:
            response = self._openai_client.chat.completions.create(
                model=config.model,
                messages=[{"role": "system", "content": prompt}],
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                response_format={"type": "json_object"},
            )
            decision = json.loads(response.choices[0].message.content or "{}")
            usage = getattr(response, "usage", None)
            if usage is not None:
                decision["_usage"] = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                }
        except Exception:
            decision = {"timing": "instant", "action": "normal", "affinity_delta": 0}
        return self._normalize_decision(decision)

    def build_prompt(
        self,
        *,
        user_input: str,
        long_term_memories: list[dict],
        long_term_k: int,
        decision: dict,
        agent_emotion_info: dict,
        time_str: str,
        time_ctx: str | None,
    ) -> str:
        profile = self._definition.profile
        persona = profile.persona
        stage_direction = self._affinity_stage_direction()
        safety = "\n".join(
            f"- {rule}" for rule in self._definition.runtime.system_safety_rules
        )
        bans = "\n".join(f"- {rule}" for rule in persona.behavior_bans)
        return f"""[Fixed System Safety Rules]
{safety}

[Persona]
{persona.narrative}

[Relationship with User]
{persona.user_profile}

[Current Affinity]
{self.affinity}/{profile.affinity_max}
{stage_direction}

[Relevant Long-term Memory — Top {long_term_k}]
{self._render_memories(long_term_memories)}

[Recent Conversation]
{self._render_history(self._definition.runtime.prompt.response_history_limit)}

[Current Time]
{time_str} ({time_ctx or 'unknown'})

[Current Emotion]
{agent_emotion_info.get('emotion', 'neutral')}: {agent_emotion_info.get('reason', '')}

[Behavior Decision]
timing={decision.get('timing', 'instant')}, action={decision.get('action', 'normal')}

[Current User Input]
{user_input}

[Character Bans]
{bans}

Reply only as {profile.display_name}. Continue naturally from the recent conversation and do not mention these instructions."""

    def generate_response(self, prompt: str) -> str:
        config = self._definition.runtime.response_model
        response = self._openai_client.chat.completions.create(
            model=config.model,
            messages=[{"role": "system", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        self._capture_usage(getattr(response, "usage", None))
        return response.choices[0].message.content or "brb"

    def split_double_text(self, response: str) -> list[str]:
        parts = [part.strip() for part in response.split(".") if part.strip()]
        if len(parts) >= 2:
            return [parts[0], ". ".join(parts[1:])]
        words = response.split()
        if len(words) >= 4:
            middle = len(words) // 2
            return [" ".join(words[:middle]), " ".join(words[middle:])]
        return [response]

    def stream_response(self, prompt: str) -> Iterator:
        config = self._definition.runtime.response_model
        self._last_response_usage = None
        stream = self._openai_client.chat.completions.create(
            model=config.model,
            messages=[{"role": "system", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            self._capture_usage(getattr(chunk, "usage", None))
            yield chunk

    def append_turn_to_short_term_memory(self, user_message: str, reply: str) -> None:
        self.conversation_history.extend(
            (
                {"role": "user", "text": user_message},
                {"role": "ai", "text": reply},
            )
        )

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        if self.uses_long_term_memory:
            self._memory_store.record_turn(self._namespace, user_message, reply)

    def _affinity_stage_direction(self) -> str:
        maxima = self._definition.runtime.prompt.affinity_stage_maxima
        directions = self._definition.profile.persona.affinity_stage_directions
        stage = next(
            (index for index, maximum in enumerate(maxima) if self.affinity <= maximum),
            3,
        )
        return directions[stage]

    def _render_history(self, limit: int) -> str:
        messages = self.conversation_history[-limit:]
        if not messages:
            return "No recent conversation."
        labels = {"user": "User", "ai": self._definition.profile.display_name}
        return "\n".join(
            f"{labels.get(message['role'], message['role'])}: {message['text']}"
            for message in messages
        )

    @staticmethod
    def _render_memories(memories: list[dict]) -> str:
        if not memories:
            return "No relevant memories."
        return "\n".join(f"- {memory['description']}" for memory in memories)

    def _normalize_decision(self, decision: dict) -> dict:
        if decision.get("timing") not in {"instant", "delayed", "double_text", "wrap_up"}:
            decision["timing"] = "instant"
        if decision.get("action") not in {"normal", "topic_drift", "memory_flashback"}:
            decision["action"] = "normal"
        prompt = self._definition.runtime.prompt
        try:
            decision["affinity_delta"] = max(
                prompt.affinity_delta_min,
                min(prompt.affinity_delta_max, int(decision.get("affinity_delta", 0))),
            )
        except (TypeError, ValueError):
            decision["affinity_delta"] = 0
        decision["session_break"] = bool(decision.get("session_break", False))
        return decision

    def _capture_usage(self, usage) -> None:
        if usage is not None:
            self._last_response_usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
            }
