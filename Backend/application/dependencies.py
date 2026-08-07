from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

from application.agent_session_registry import AgentSessionRegistry
from application.friend_session_registry import FriendSessionRegistry
from application.services.agent_catalog_service import (
    AgentCatalogService,
    AgentNotFoundError,
)
from application.services.friend_chat_service import FriendChatService
from application.services.lesson_chat_service import LessonChatService
from application.services.autorater_service import AutoraterService
from domain.agents.jiho import JIHO_DEFINITION


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = BACKEND_DIR / "assets" / "Examples"
FOCUSED_EXAMPLES_DIR = BACKEND_DIR / "assets" / "FocusedPractice"


def _session_limit() -> int:
    return max(1, int(os.getenv("CHAT_SESSION_MAX_ENTRIES", "256")))


def _session_ttl_seconds() -> float:
    return max(1.0, float(os.getenv("CHAT_SESSION_TTL_SECONDS", "3600")))


@lru_cache(maxsize=1)
def _get_openai_client():
    from openai import OpenAI

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be configured in .env")
    return OpenAI(api_key=api_key)


class _LazyOpenAIClient:
    @property
    def chat(self):
        return _get_openai_client().chat


@lru_cache(maxsize=1)
def _get_agent_repository():
    from infrastructure.repositories.in_memory_agent_repository import (
        InMemoryConversationAgentRepository,
    )

    return InMemoryConversationAgentRepository((JIHO_DEFINITION,))


@lru_cache(maxsize=1)
def _get_agent_memory_store():
    from infrastructure.storage.namespaced_conversation_memory import (
        NamespacedConversationMemoryStore,
    )

    return NamespacedConversationMemoryStore()


@lru_cache(maxsize=1)
def _get_agent_creation_service():
    from application.services.agent_creation_service import (
        ConversationAgentCreationService,
    )
    from infrastructure.adapters.openai_agent_designer import (
        OpenAIConversationAgentDesigner,
    )

    return ConversationAgentCreationService(
        OpenAIConversationAgentDesigner(_LazyOpenAIClient())
    )


@lru_cache(maxsize=1)
def _get_agent_catalog_service() -> AgentCatalogService:
    return AgentCatalogService(
        _get_agent_repository(),
        _get_agent_creation_service(),
    )


def _create_configurable_agent_service(definition, user_id: str) -> FriendChatService:
    from infrastructure.adapters.configurable_conversation_agent import (
        ConfigurableConversationAgent,
    )
    from infrastructure.adapters.configurable_conversation_runtime import (
        ConfigurableConversationRuntime,
    )

    runtime = ConfigurableConversationRuntime(
        definition=definition,
        user_id=user_id,
        openai_client=_get_openai_client(),
        memory_store=_get_agent_memory_store(),
    )
    return FriendChatService(
        ConfigurableConversationAgent(definition=definition, runtime=runtime)
    )


@lru_cache(maxsize=1)
def _get_agent_sessions() -> AgentSessionRegistry:
    return AgentSessionRegistry(
        _get_agent_repository(),
        _create_configurable_agent_service,
        ttl_seconds=_session_ttl_seconds(),
        max_sessions=_session_limit(),
    )


@lru_cache(maxsize=1)
def _get_friend_sessions() -> FriendSessionRegistry:
    from infrastructure.adapters.jiho_legacy_adapter import JihoLegacyAdapter

    return FriendSessionRegistry(
        lambda: FriendChatService(JihoLegacyAdapter()),
        ttl_seconds=_session_ttl_seconds(),
        max_sessions=_session_limit(),
    )


@lru_cache(maxsize=1)
def _get_lesson_chat_service() -> LessonChatService:
    from application.prompts.lesson_prompt_builder import LessonPromptBuilder
    from infrastructure.adapters.teacher_agent import TeacherAgent
    from infrastructure.clients.openai_lesson_tutor_client import OpenAILessonTutorClient
    from infrastructure.repositories.file_lesson_transcript_repository import (
        FileLessonTranscriptRepository,
    )

    teacher = TeacherAgent(
        transcript_repository=FileLessonTranscriptRepository(
            BACKEND_DIR / "data" / "script_new.txt"
        ),
        prompt_builder=LessonPromptBuilder(),
        tutor_client=OpenAILessonTutorClient(_get_openai_client()),
    )
    return LessonChatService(teacher)


@lru_cache(maxsize=1)
def _get_autorater_service() -> AutoraterService:
    from infrastructure.adapters.isabella_solver_agent import (
        create_legacy_backed_isabella_agent,
    )
    from infrastructure.storage.temp_image_storage import TempImageStorage

    return AutoraterService(
        create_legacy_backed_isabella_agent(),
        TempImageStorage(),
        EXAMPLES_DIR,
        FOCUSED_EXAMPLES_DIR,
    )


def get_friend_chat_service(
    session_id: Annotated[str | None, Header(alias="X-Session-ID")] = None,
) -> FriendChatService:
    return _get_friend_sessions().get(session_id)


def get_agent_catalog_service() -> AgentCatalogService:
    return _get_agent_catalog_service()


def get_agent_chat_service(
    agent_id: str,
    session_id: Annotated[str | None, Header(alias="X-Session-ID")] = None,
    user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> FriendChatService:
    try:
        return _get_agent_sessions().get(agent_id, session_id, user_id)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' was not found.",
        ) from exc


def get_lesson_chat_service() -> LessonChatService:
    return _get_lesson_chat_service()


def get_autorater_service() -> AutoraterService:
    return _get_autorater_service()
