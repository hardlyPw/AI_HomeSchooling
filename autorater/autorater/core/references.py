from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from autorater.core.schemas import GoodExample, NormalizedRow
from autorater.core.utils import clean_text, read_jsonl, stable_hash


CORE_TAGS = {
    "one_question",
    "no_answer_leak",
    "small_hint",
    "source_grounded",
    "gentle_correction",
    "check_understanding",
}

KEYWORD_SIGNALS = [
    (("wrong", "mistake", "incorrect", "calculated", "error", "틀렸", "실수"), {"error_localization", "gentle_correction"}),
    (("understand", "explain", "why", "think", "이해", "설명"), {"check_understanding"}),
    (("context", "rag", "source", "unsupported", "hallucinate", "맥락", "근거"), {"source_grounded"}),
    (("answer", "final", "give", "정답", "답을"), {"no_answer_leak", "small_hint"}),
    (("correct", "actually", "thanks", "correction", "맞아", "수정"), {"accept_correction", "controlled_confirmation"}),
    (("question", "questions", "물음", "질문"), {"one_question"}),
]


def load_good_examples(path: str | Path) -> list[GoodExample]:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"Good examples file does not exist: {file_path}")
    examples: list[GoodExample] = []
    for idx, row in enumerate(read_jsonl(file_path), 1):
        example_id = clean_text(row.get("id")) or f"good_{idx:04d}"
        tags = row.get("criteria_tags") if isinstance(row.get("criteria_tags"), list) else []
        messages = row.get("messages") if isinstance(row.get("messages"), list) else []
        ideal = clean_text(row.get("ideal_assistant"))
        if not ideal and messages:
            for msg in reversed(messages):
                if isinstance(msg, dict) and str(msg.get("role") or "").lower() == "assistant":
                    ideal = clean_text(msg.get("content"))
                    break
        examples.append(
            GoodExample(
                id=example_id,
                category=clean_text(row.get("category")),
                source=clean_text(row.get("source")),
                input=clean_text(row.get("input"), max_chars=700),
                context=clean_text(row.get("context"), max_chars=900),
                ideal_assistant=ideal,
                criteria_tags=[clean_text(tag) for tag in tags if clean_text(tag)],
                why_good=clean_text(row.get("why_good"), max_chars=500),
                watch_out_for=clean_text(row.get("watch_out_for"), max_chars=500),
                raw=row,
            )
        )
    if not examples:
        raise ValueError(f"No good examples found in {file_path}")
    return examples


class ReferenceSelector:
    def __init__(self, examples: Iterable[GoodExample]):
        self.examples = list(examples)

    def select_for_row(
        self,
        row: NormalizedRow,
        criteria_prompt: str,
        *,
        max_examples: int = 10,
    ) -> list[GoodExample]:
        desired = self._desired_tags(row, criteria_prompt)
        scored = []
        for example in self.examples:
            tags = set(example.criteria_tags)
            category = example.category
            score = 0
            score += 4 * len(tags & desired)
            if category in desired:
                score += 4
            score += 2 * len(tags & CORE_TAGS)
            if category in CORE_TAGS:
                score += 2
            tie = stable_hash(row.row_id, criteria_prompt, example.id, length=10)
            scored.append((score, tie, example))

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected: list[GoodExample] = []
        source_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        source_limit = max(2, (max_examples + 2) // 3)

        for _score, _tie, example in scored:
            if len(selected) >= max_examples:
                break
            source = example.source or "unknown"
            category = example.category or "unknown"
            if source_counts[source] >= source_limit and len(selected) < max_examples - 2:
                continue
            if category_counts[category] >= 3 and len(selected) < max_examples - 2:
                continue
            selected.append(example)
            source_counts[source] += 1
            category_counts[category] += 1

        if len(selected) < max_examples:
            selected_ids = {example.id for example in selected}
            leftovers = [example for _score, _tie, example in scored if example.id not in selected_ids]
            leftovers.sort(key=lambda example: stable_hash(row.row_id, criteria_prompt, example.id, length=10))
            selected.extend(leftovers[: max_examples - len(selected)])
        return selected[:max_examples]

    def select_for_dataset(self, criteria_prompt: str, *, max_examples: int = 12) -> list[GoodExample]:
        pseudo = NormalizedRow(row_id="dataset_level", input=criteria_prompt, context="", target_assistant="")
        return self.select_for_row(pseudo, criteria_prompt, max_examples=max_examples)

    def _desired_tags(self, row: NormalizedRow, criteria_prompt: str) -> set[str]:
        text = " ".join(
            [
                row.input,
                row.context,
                row.target_assistant,
                criteria_prompt,
            ]
        ).lower()
        desired: set[str] = set(CORE_TAGS)
        for keywords, tags in KEYWORD_SIGNALS:
            if any(keyword in text for keyword in keywords):
                desired.update(tags)
        return desired


def compact_examples(examples: list[GoodExample]) -> list[dict[str, object]]:
    return [
        {
            "id": example.id,
            "category": example.category,
            "source": example.source,
            "input": example.input,
            "context": example.context,
            "ideal_assistant": example.ideal_assistant,
            "criteria_tags": example.criteria_tags,
            "why_good": example.why_good,
            "watch_out_for": example.watch_out_for,
        }
        for example in examples
    ]
