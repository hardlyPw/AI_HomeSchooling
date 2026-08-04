from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.expiring_service_cache import ExpiringServiceCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class ExpiringServiceCacheTest(unittest.TestCase):
    def test_reuses_active_entry_and_recreates_expired_entry(self) -> None:
        clock = FakeClock()
        cache = ExpiringServiceCache[str, object](
            ttl_seconds=10,
            max_entries=2,
            clock=clock,
        )

        first = cache.get_or_create("session", object)
        clock.now = 9
        self.assertIs(first, cache.get_or_create("session", object))
        clock.now = 20
        recreated = cache.get_or_create("session", object)

        self.assertIsNot(first, recreated)
        self.assertEqual(cache.size, 1)

    def test_evicts_least_recently_used_entry_at_capacity(self) -> None:
        clock = FakeClock()
        cache = ExpiringServiceCache[str, object](
            ttl_seconds=100,
            max_entries=2,
            clock=clock,
        )

        first = cache.get_or_create("first", object)
        clock.now = 1
        second = cache.get_or_create("second", object)
        clock.now = 2
        self.assertIs(first, cache.get_or_create("first", object))
        clock.now = 3
        cache.get_or_create("third", object)

        self.assertEqual(cache.size, 2)
        self.assertIsNot(second, cache.get_or_create("second", object))


if __name__ == "__main__":
    unittest.main()
