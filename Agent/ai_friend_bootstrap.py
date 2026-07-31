from __future__ import annotations

import atexit
from dataclasses import dataclass
from functools import lru_cache
import os
import sys
from typing import Any
import weakref

from dotenv import load_dotenv

from ai_friend_state import JihoRuntimeState
from jiho_memory_repository import JihoMemoryRepository


MEMORY_TABLE = "friend_memories_v2"
MEMORY_MATCH_RPC = "match_friend_memories_v2"
SESSION_TIMEOUT_SECONDS = 5 * 60


@dataclass(frozen=True)
class AIFriendDependencies:
    """Process-wide external clients shared by conversation runtimes."""

    supabase: Any
    openai_client: Any
    embedding_model: Any


@dataclass
class AIFriendRuntimeContext:
    """Session-owned state and memory consumed by backend runtime adapters."""

    supabase: Any
    openai_client: Any
    embedding_model: Any
    runtime_state: JihoRuntimeState
    _memory_repository: JihoMemoryRepository
    USE_LONG_TERM_MEMORY: bool = True
    DEBUG_PROMPT: bool = False


_memory_repositories: weakref.WeakSet[JihoMemoryRepository] = weakref.WeakSet()


def configure_console_encoding() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


@lru_cache(maxsize=1)
def load_ai_friend_dependencies() -> AIFriendDependencies:
    """Create expensive external clients once for the current process."""

    from openai import OpenAI
    from sentence_transformers import SentenceTransformer
    from supabase import create_client

    configure_console_encoding()
    load_dotenv()

    supabase_url = str(os.getenv("SUPABASE_URL", ""))
    supabase_key = str(os.getenv("SUPABASE_KEY", ""))
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured in .env")

    openai_key = str(os.getenv("OPENAI_API_KEY", ""))
    if not openai_key:
        raise ValueError("OPENAI_API_KEY must be configured in .env")

    print("Loading embedding model...")
    embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("Embedding model loaded.")

    return AIFriendDependencies(
        supabase=create_client(supabase_url, supabase_key),
        openai_client=OpenAI(api_key=openai_key),
        embedding_model=embedding_model,
    )


def create_ai_friend_runtime_context(
    *,
    dependencies: AIFriendDependencies | None = None,
    uses_long_term_memory: bool = True,
    debug_prompt: bool = False,
) -> AIFriendRuntimeContext:
    """Create isolated mutable state while reusing process-wide clients."""

    resolved = dependencies or load_ai_friend_dependencies()
    repository = JihoMemoryRepository(
        supabase_client=resolved.supabase,
        embedding_model=resolved.embedding_model,
        openai_client=resolved.openai_client,
        memory_table=MEMORY_TABLE,
        memory_match_rpc=MEMORY_MATCH_RPC,
        session_timeout_seconds=SESSION_TIMEOUT_SECONDS,
        uses_long_term_memory=lambda: uses_long_term_memory,
    )
    _memory_repositories.add(repository)
    return AIFriendRuntimeContext(
        supabase=resolved.supabase,
        openai_client=resolved.openai_client,
        embedding_model=resolved.embedding_model,
        runtime_state=JihoRuntimeState(),
        _memory_repository=repository,
        USE_LONG_TERM_MEMORY=uses_long_term_memory,
        DEBUG_PROMPT=debug_prompt,
    )


def shutdown_ai_friend_memories() -> None:
    for repository in list(_memory_repositories):
        repository.shutdown()


atexit.register(shutdown_ai_friend_memories)
