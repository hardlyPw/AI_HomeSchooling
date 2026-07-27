from __future__ import annotations

from pathlib import Path

from application.services.autorater_service import AutoraterService
from application.services.friend_chat_service import FriendChatService
from application.services.lesson_chat_service import LessonChatService
from infrastructure.adapters.autorater_legacy_adapter import AutoraterLegacyAdapter
from infrastructure.adapters.jiho_legacy_adapter import JihoLegacyAdapter
from infrastructure.adapters.teacher_legacy_adapter import TeacherLegacyAdapter
from infrastructure.storage.temp_image_storage import TempImageStorage


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = BACKEND_DIR / "assets" / "Examples"

_friend_chat_service = FriendChatService(JihoLegacyAdapter())
_lesson_chat_service = LessonChatService(TeacherLegacyAdapter())
_autorater_service = AutoraterService(
    AutoraterLegacyAdapter(),
    TempImageStorage(),
    EXAMPLES_DIR,
)


def get_friend_chat_service() -> FriendChatService:
    return _friend_chat_service


def get_lesson_chat_service() -> LessonChatService:
    return _lesson_chat_service


def get_autorater_service() -> AutoraterService:
    return _autorater_service
