from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


def load_ai_friend_module() -> ModuleType:
    """Load the legacy Agent/AI_Friend.py module from the workspace."""

    agent_dir = Path(__file__).resolve().parents[3] / "Agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))

    import AI_Friend as af  # noqa: E402

    af.DEBUG_PROMPT = False
    return af
