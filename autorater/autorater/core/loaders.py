from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from autorater.core.schemas import NormalizedRow
from autorater.core.utils import clean_text, read_jsonl, stable_hash


TARGET_KEYS = [
    "target_assistant",
    "ideal_assistant",
    "assistant",
    "assistant_response",
    "model_output",
    "output",
    "response",
    "completion",
    "rewritten_assistant",
]

TRANSCRIPT_TARGET_KEYS = [
    "isabella_displayed",
    "isabella_raw",
    "isabella_for_memory",
    *TARGET_KEYS,
]

INPUT_KEYS = [
    "input",
    "user_input",
    "student_input",
    "prompt",
    "question",
    "query",
    "instruction",
]

CONTEXT_KEYS = [
    "context",
    "source_context",
    "dialogue_context",
    "conversation_context",
    "original_response",
]

ID_KEYS = ["id", "row_id", "example_id", "source_id", "uid", "test_id"]


def load_dataset(path: str | Path, fmt: str = "auto") -> tuple[list[NormalizedRow], str]:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset does not exist: {file_path}")
    detected = _detect_format(file_path, fmt)
    if detected == "jsonl":
        raw_rows = read_jsonl(file_path)
    elif detected == "json":
        raw_rows = _read_json_rows(file_path)
    elif detected == "csv":
        raw_rows = _read_csv_rows(file_path)
    else:
        raise ValueError(f"Unsupported dataset format: {detected}")
    raw_rows = _expand_transcript_runs(raw_rows)
    rows = [_normalize_row(row, idx) for idx, row in enumerate(raw_rows, 1)]
    return rows, detected


def _detect_format(path: Path, fmt: str) -> str:
    requested = str(fmt or "auto").lower()
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    return "jsonl"


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = value.get("rows") or value.get("data") or value.get("examples") or value.get("items")
    else:
        rows = None
    if not isinstance(rows, list):
        raise ValueError(f"JSON dataset must be a list or contain rows/data/examples/items: {path}")
    return [row for row in rows if isinstance(row, dict)]


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _expand_transcript_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        if _is_transcript_run(row):
            expanded.extend(_transcript_run_to_rows(row, index))
        else:
            expanded.append(row)
    return expanded


def _is_transcript_run(row: dict[str, Any]) -> bool:
    return isinstance(row.get("opener"), dict) or isinstance(row.get("turns"), list)


def _transcript_run_to_rows(run: dict[str, Any], run_index: int) -> list[dict[str, Any]]:
    base_id = _first_text(run, ID_KEYS) or f"run_{run_index:05d}"
    context_header = _transcript_context_header(run)
    rows: list[dict[str, Any]] = []
    history: list[dict[str, str]] = []

    opener = run.get("opener")
    if isinstance(opener, dict):
        target = _first_text(opener, TRANSCRIPT_TARGET_KEYS)
        if target:
            opener_input = _first_text(run, ["question_text", "question", "input", "prompt"]) or _first_text(
                opener, ["user_message", "input", "prompt"]
            )
            messages = _messages_with_current(history, None, target)
            rows.append(
                _transcript_row(
                    run=run,
                    segment=opener,
                    row_id=f"{base_id}__line{run_index:05d}__opener",
                    input_text=opener_input,
                    context=_join_context(context_header, "Turn type: opener"),
                    target=target,
                    messages=messages,
                    turn_type="opener",
                )
            )
            history.append({"role": "assistant", "content": target})

    turns = run.get("turns")
    if isinstance(turns, list):
        for turn_number, turn in enumerate(turns, 1):
            if not isinstance(turn, dict):
                continue
            target = _first_text(turn, TRANSCRIPT_TARGET_KEYS)
            if not target:
                continue
            user_text = _first_text(turn, ["user", "user_message", "input", "student_input", "prompt"])
            turn_context = _join_context(
                context_header,
                f"Turn type: dialogue turn {turn_number}",
                _dialogue_history_text(history),
            )
            messages = _messages_with_current(history, user_text, target)
            rows.append(
                _transcript_row(
                    run=run,
                    segment=turn,
                    row_id=f"{base_id}__line{run_index:05d}__turn_{turn_number:03d}",
                    input_text=user_text,
                    context=turn_context,
                    target=target,
                    messages=messages,
                    turn_type="turn",
                )
            )
            if user_text:
                history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": target})

    return rows or [run]


def _transcript_row(
    *,
    run: dict[str, Any],
    segment: dict[str, Any],
    row_id: str,
    input_text: str,
    context: str,
    target: str,
    messages: list[dict[str, str]],
    turn_type: str,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "input": input_text,
        "context": context,
        "target_assistant": target,
        "messages": messages,
        "source_format": "run_transcript",
        "turn_type": turn_type,
        "test_id": run.get("test_id"),
        "question_text": run.get("question_text"),
        "canonical_answer": run.get("canonical_answer"),
        "eop": segment.get("eop"),
        "raw_run_metadata": {
            key: run.get(key)
            for key in [
                "test_id",
                "question_text",
                "canonical_answer",
                "stance",
                "student_archetype",
                "isabella_model",
                "simulator_model",
                "eop_fired",
                "eop_turn_idx",
                "timestamp",
            ]
            if key in run
        },
        "raw_segment": segment,
    }


def _transcript_context_header(run: dict[str, Any]) -> str:
    fields = [
        ("Question", run.get("question_text")),
        ("Canonical answer", run.get("canonical_answer")),
        ("Student archetype", run.get("student_archetype")),
        ("Stance", run.get("stance")),
        ("Isabella model", run.get("isabella_model")),
        ("Simulator model", run.get("simulator_model")),
    ]
    return "\n".join(f"{label}: {clean_text(value, max_chars=700)}" for label, value in fields if clean_text(value))


def _messages_with_current(history: list[dict[str, str]], user_text: str | None, target: str) -> list[dict[str, str]]:
    messages = list(history)
    if user_text:
        messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": target})
    return messages


def _dialogue_history_text(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    lines = []
    for message in history[-10:]:
        role = clean_text(message.get("role"))
        content = clean_text(message.get("content"), max_chars=500)
        if role and content:
            lines.append(f"{role}: {content}")
    return "Previous dialogue:\n" + "\n".join(lines)


def _join_context(*parts: str) -> str:
    return "\n\n".join(clean_text(part, max_chars=4000) for part in parts if clean_text(part))


def _normalize_row(row: dict[str, Any], index: int) -> NormalizedRow:
    messages = row.get("messages") if isinstance(row.get("messages"), list) else []
    target_from_messages, input_from_messages, context_from_messages = _extract_from_messages(messages)
    target = _first_text(row, TARGET_KEYS) or target_from_messages
    input_text = _first_text(row, INPUT_KEYS) or input_from_messages
    context = _first_text(row, CONTEXT_KEYS) or context_from_messages
    row_id = _first_text(row, ID_KEYS)
    if not row_id:
        row_id = f"row_{index:05d}_{stable_hash(input_text, target, index, length=8)}"
    return NormalizedRow(
        row_id=str(row_id),
        input=input_text,
        context=context,
        target_assistant=target,
        messages=[msg for msg in messages if isinstance(msg, dict)],
        raw=row,
    )


def _first_text(row: dict[str, Any], keys: list[str]) -> str:
    lowered = {str(key).lower(): key for key in row.keys()}
    for key in keys:
        actual = lowered.get(key.lower())
        if actual is None:
            continue
        text = clean_text(row.get(actual))
        if text:
            return text
    return ""


def _extract_from_messages(messages: list[Any]) -> tuple[str, str, str]:
    if not messages:
        return "", "", ""
    clean_messages = [msg for msg in messages if isinstance(msg, dict)]
    last_assistant_index = -1
    for idx, msg in enumerate(clean_messages):
        if str(msg.get("role") or "").lower() == "assistant" and clean_text(msg.get("content")):
            last_assistant_index = idx
    target = ""
    user_input = ""
    context_lines: list[str] = []
    if last_assistant_index >= 0:
        target = clean_text(clean_messages[last_assistant_index].get("content"))
        for prev in reversed(clean_messages[:last_assistant_index]):
            if str(prev.get("role") or "").lower() == "user" and clean_text(prev.get("content")):
                user_input = clean_text(prev.get("content"))
                break
        for msg in clean_messages[:last_assistant_index]:
            role = clean_text(msg.get("role"))
            content = clean_text(msg.get("content"), max_chars=800)
            if role and content:
                context_lines.append(f"{role}: {content}")
    return target, user_input, "\n".join(context_lines)
