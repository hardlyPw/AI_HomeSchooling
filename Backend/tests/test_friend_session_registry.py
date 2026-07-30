from __future__ import annotations

from pathlib import Path
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.friend_session_registry import FriendSessionRegistry


class FriendSessionRegistryTest(unittest.TestCase):
    def test_reuses_service_within_session_and_isolates_other_sessions(self) -> None:
        created: list[object] = []

        def create_service():
            service = object()
            created.append(service)
            return service

        registry = FriendSessionRegistry(create_service)

        first = registry.get("session-a")
        same = registry.get("session-a")
        other = registry.get("session-b")

        self.assertIs(first, same)
        self.assertIsNot(first, other)
        self.assertEqual(len(created), 2)

    def test_blank_session_ids_share_default_session(self) -> None:
        registry = FriendSessionRegistry(object)

        self.assertIs(registry.get(None), registry.get(" "))


if __name__ == "__main__":
    unittest.main()
