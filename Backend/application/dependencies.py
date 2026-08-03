from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

from application.agent_session_registry import AgentSessionRegistry
from application.friend_session_registry import FriendSessionRegistry
from application.services.agent_catalog_service import (
    AgentCatalogService,
    AgentNotFoundError,
)
from application.services.agent_creation_service import ConversationAgentCreationService
from application.services.autorater_service import AutoraterService
from application.services.friend_chat_service import FriendChatService
from application.services.lesson_chat_service import LessonChatService
from infrastructure.adapters.autorater_legacy_adapter import AutoraterLegacyAdapter
from infrastructure.adapters.jiho_legacy_adapter import JihoLegacyAdapter
from infrastructure.adapters.configurable_conversation_agent import (
    ConfigurableConversationAgent,
)
from infrastructure.adapters.configurable_conversation_runtime import (
    ConfigurableConversationRuntime,
)
from infrastructure.adapters.openai_agent_designer import OpenAIConversationAgentDesigner
from infrastructure.repositories.in_memory_agent_repository import (
    InMemoryConversationAgentRepository,
)
from infrastructure.storage.namespaced_conversation_memory import (
    NamespacedConversationMemoryStore,
)
from infrastructure.adapters.teacher_legacy_adapter import TeacherLegacyAdapter
from infrastructure.storage.temp_image_storage import TempImageStorage
from domain.agents.jiho import JIHO_DEFINITION


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = BACKEND_DIR / "assets" / "Examples"

_friend_sessions = FriendSessionRegistry(
    lambda: FriendChatService(JihoLegacyAdapter())
)
_agent_repository = InMemoryConversationAgentRepository((JIHO_DEFINITION,))
_agent_memory_store = NamespacedConversationMemoryStore()


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


_agent_creation_service = ConversationAgentCreationService(
    OpenAIConversationAgentDesigner(_LazyOpenAIClient())
)
_agent_catalog_service = AgentCatalogService(
    _agent_repository,
    _agent_creation_service,
)


def _create_configurable_agent_service(definition, user_id: str) -> FriendChatService:
    runtime = ConfigurableConversationRuntime(
        definition=definition,
        user_id=user_id,
        openai_client=_get_openai_client(),
        memory_store=_agent_memory_store,
    )
    return FriendChatService(
        ConfigurableConversationAgent(
            definition=definition,
            runtime=runtime,
        )
    )


_agent_sessions = AgentSessionRegistry(
    _agent_repository,
    _create_configurable_agent_service,
)
_lesson_chat_service = LessonChatService(TeacherLegacyAdapter())
_autorater_service = AutoraterService(
    AutoraterLegacyAdapter(),
    TempImageStorage(),
    EXAMPLES_DIR,
)


def get_friend_chat_service(
    session_id: Annotated[
        str | None,
        Header(alias="X-Session-ID"),
    ] = None,
) -> FriendChatService:
    return _friend_sessions.get(session_id)


def get_agent_catalog_service() -> AgentCatalogService:
    return _agent_catalog_service


def get_agent_chat_service(
    agent_id: str,
    session_id: Annotated[str | None, Header(alias="X-Session-ID")] = None,
    user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> FriendChatService:
    try:
        return _agent_sessions.get(agent_id, session_id, user_id)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' was not found.",
        ) from exc


def get_lesson_chat_service() -> LessonChatService:
    return _lesson_chat_service


def get_autorater_service() -> AutoraterService:
    return _autorater_service
