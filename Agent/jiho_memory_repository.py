from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import threading
import time
from typing import Any, cast


class JihoMemoryRepository:
    """Supabase-backed long-term memory repository for Jiho conversations."""

    def __init__(
        self,
        *,
        supabase_client,
        embedding_model,
        openai_client,
        memory_table: str,
        memory_match_rpc: str,
        session_timeout_seconds: int,
        uses_long_term_memory: Callable[[], bool],
    ) -> None:
        self._supabase = supabase_client
        self._embedding_model = embedding_model
        self._openai_client = openai_client
        self._memory_table = memory_table
        self._memory_match_rpc = memory_match_rpc
        self._session_timeout_seconds = session_timeout_seconds
        self._uses_long_term_memory = uses_long_term_memory
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory")
        self._pending_chunk_lock = threading.Lock()
        self._pending_chunk: list[dict] = []
        self._session_timer_lock = threading.Lock()
        self._session_timer: threading.Timer | None = None

    def get_long_term_memory(self, query_text: str, top_k: int = 5) -> list[dict]:
        start_embed = time.time()
        query_vector = self._embedding_model.encode(query_text).tolist()
        print(f"[Latency] 임베딩 변환: {time.time() - start_embed:.4f}초")

        start_db = time.time()
        response = self._supabase.rpc(
            self._memory_match_rpc,
            {
                "query_embedding": query_vector,
                "match_threshold": 0.0,
                "match_count": 50,
            },
        ).execute()
        print(f"[Latency] 장기기억 검색: {time.time() - start_db:.4f}초")

        candidates = cast(list[dict[str, Any]], response.data) if isinstance(response.data, list) else []
        if not candidates:
            return []

        now = datetime.now(timezone.utc)
        temp_list = []
        for item in candidates:
            rel_raw = float(item.get("similarity", 0.0))
            imp_raw = float(item.get("poignancy", 3.0))
            created_at_str = item.get("created_at")
            if isinstance(created_at_str, str):
                created_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                hours_passed = max(0.0, (now - created_time).total_seconds() / 3600.0)
            else:
                hours_passed = 1000.0
            rec_raw = float(math.pow(0.99, hours_passed))
            temp_list.append({"item": item, "rel_raw": rel_raw, "imp_raw": imp_raw, "rec_raw": rec_raw})

        def normalize(values: list[float]) -> list[float]:
            min_val, max_val = min(values), max(values)
            if max_val == min_val:
                return [1.0] * len(values)
            return [(value - min_val) / (max_val - min_val) for value in values]

        rel_norm = normalize([x["rel_raw"] for x in temp_list])
        imp_norm = normalize([x["imp_raw"] for x in temp_list])
        rec_norm = normalize([x["rec_raw"] for x in temp_list])

        scored = []
        for index, item in enumerate(temp_list):
            total = rel_norm[index] * 5 + imp_norm[index] * 1 + rec_norm[index] * 0.3
            original = item["item"]
            scored.append(
                {
                    "description": str(original.get("description", "")),
                    "score": round(total, 3),
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_k]
        for index, memory in enumerate(top, 1):
            print(f"[Memory] TOP{index}: {memory['description']}, score={memory['score']}")
        return top

    def drain_pending_chunk(self) -> list[dict]:
        with self._pending_chunk_lock:
            chunk = list(self._pending_chunk)
            self._pending_chunk.clear()
        return chunk

    def record_turn(self, user_text: str, ai_text: str, session_break: bool = False) -> None:
        if not self._uses_long_term_memory():
            return
        with self._pending_chunk_lock:
            self._pending_chunk.append(
                {
                    "user": user_text,
                    "ai": ai_text,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
            pending_count = len(self._pending_chunk)
        print(f"[Memory] turn 누적: {pending_count} (session 단위 flush 대기)")
        if session_break:
            with self._session_timer_lock:
                if self._session_timer is not None:
                    self._session_timer.cancel()
                    self._session_timer = None
            self._trigger_session_end_async("session_break")
            return
        self._reset_session_timer()

    def shutdown(self) -> None:
        if self._uses_long_term_memory():
            with self._session_timer_lock:
                if self._session_timer is not None:
                    self._session_timer.cancel()
            self._trigger_session_end()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _save_memory(self, memory_type: str, description: str, poignancy: int) -> None:
        try:
            embedding = self._embedding_model.encode(description).tolist()
            self._supabase.table(self._memory_table).insert(
                {
                    "type": memory_type,
                    "description": description,
                    "embedding_vector": embedding,
                    "poignancy": poignancy,
                }
            ).execute()
            print(f"[Memory] {memory_type} 저장 (poignancy={poignancy}): {description[:60]}...")
        except Exception as exc:
            print(f"[Memory] 저장 실패 ({memory_type}): {exc!s:.200s}")

    def _trigger_session_end(self) -> None:
        print("[Memory] 세션 종료 감지 (chat 마무리)")
        chunk = self.drain_pending_chunk()
        if not chunk:
            return
        self._create_chat_memory(chunk)

    def _trigger_session_end_async(self, reason: str) -> None:
        chunk = self.drain_pending_chunk()
        if not chunk:
            return
        print(f"[Memory] 세션 종료 ({reason}) → chat async 추출")
        self._executor.submit(self._create_chat_memory, chunk)

    def _create_chat_memory(self, chunk: list[dict]) -> None:
        convo_text = "\n".join(
            f"User: {turn['user']}\nJiho: {turn['ai']}"
            for turn in chunk
        )

        try:
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract distinct factual memories from a chat session. "
                            "Output only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"[Chat Log]\n{convo_text}\n\n"
                            "[Task]\n"
                            "Extract AT MOST 3 memory entries from this entire session. "
                            "Return an empty list if the session is small talk with nothing "
                            "referenceable later.\n\n"
                            "[DIVERSIFICATION rule — critical]\n"
                            "Each entry MUST cover a DIFFERENT angle (different person, event, "
                            "decision, fact, OR feeling). Never paraphrase the same event from "
                            "another wording. If the session has only 1 distinct angle, return "
                            "1 entry — don't pad with rewordings. Use 2 only when there are "
                            "clearly separate angles, 3 only in rich sessions.\n\n"
                            "[DETAIL rule]\n"
                            "Each entry: 1-2 sentences, self-contained. Include who, what, "
                            "where, and what the user felt/decided. A future reader should "
                            "understand the entry without seeing the original chat log. Concrete "
                            "details (specific game/song/place/teacher/friend) > abstract summaries.\n\n"
                            "[NAMED ENTITY rule]\n"
                            "PRESERVE names verbatim when present: friends (Leo, Jules, Nina, "
                            "Chris, Ryan, Ethan, Maya, etc.), teachers (Ms. Lin, Mrs. Kim, "
                            "Ms. Carter, Coach Reed, etc.), games (LoL, Valorant, Minecraft, "
                            "Ahri, Faker), places (Split, etc.), songs, brands. Do NOT generalize "
                            "to 'a friend', 'his classmate', 'a teacher', 'a game'.\n\n"
                            "[VOICE rule]\n"
                            "- Third-person factual notes about the user.\n"
                            "- Don't include 'Jiho' or 'the AI said' (the persona itself). "
                            "Other people's names ARE included per the rule above.\n"
                            "- No meta-commentary.\n\n"
                            "[GOOD example — 3 entries on different angles]\n"
                            "- \"User queued Ahri mid late at night and tunnel-visioned on minions, "
                            "getting ganked twice; Ryan called him out for it.\"\n"
                            "- \"User's mom interrupted during champ select to ask about unfinished "
                            "math corrections, then gave the disappointed look.\"\n"
                            "- \"User decided to review a replay instead of spam queueing tilted, "
                            "and wants to hit gold before break.\"\n\n"
                            "[BAD example — paraphrasing same event 3 times, do NOT do this]\n"
                            "- \"User struggled with Ahri mid and got ganked.\"\n"
                            "- \"User played Ahri and felt unfairly ganked twice.\"\n"
                            "- \"User had a tough Ahri mid game with multiple ganks.\"\n\n"
                            "[Poignancy 1-5]\n"
                            "- 1: small talk, nothing referenceable later (omit instead)\n"
                            "- 2: minor detail, low future relevance\n"
                            "- 3: ordinary, contains a concrete fact\n"
                            "- 4: notable — recurring theme OR clear emotional weight\n"
                            "- 5: emotionally intense OR a major decision/event for the user\n\n"
                            'Output JSON: {"entries": [{"description": "...", "poignancy": <1-5>}, ...]}'
                        ),
                    },
                ],
                max_tokens=1200,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            parsed = json.loads(raw)
            entries = parsed.get("entries", [])
            if not isinstance(entries, list):
                print("[Memory] chat 추출 결과 형식 오류")
                return
        except Exception as exc:
            print(f"[Memory] chat description 생성 실패: {exc!s:.200s}")
            return

        saved = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            description = str(entry.get("description", "")).strip()
            if not description:
                continue
            try:
                poignancy = max(1, min(5, int(entry.get("poignancy", 3))))
            except (TypeError, ValueError):
                poignancy = 3
            self._save_memory("chat", description, poignancy)
            saved += 1

        if saved == 0:
            print("[Memory] chat 추출 결과 없음 (filler chunk)")
        else:
            print(f"[Memory] chat description {saved}개 저장")

    def _reset_session_timer(self) -> None:
        with self._session_timer_lock:
            if self._session_timer is not None:
                self._session_timer.cancel()
            self._session_timer = threading.Timer(
                self._session_timeout_seconds,
                self._trigger_session_end,
            )
            self._session_timer.daemon = True
            self._session_timer.start()
