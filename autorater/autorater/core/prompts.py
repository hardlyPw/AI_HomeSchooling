from __future__ import annotations

import json
from collections import Counter
from typing import Any

from autorater.core.references import compact_examples
from autorater.core.schemas import GoodExample, NormalizedRow, RowEvaluation, TargetResult
from autorater.core.utils import clean_text


POSITIVE_REFERENCE_NOTICE = (
    "The provided good examples are positive references, not training data and not an exhaustive rubric. "
    "Use them to calibrate style and policy, but score the target dataset against the written evaluation criteria."
)


ROW_BATCH_RESPONSE_SCHEMA = {
    "row_evaluations": [
        {
            "row_id": "string",
            "score": "number from 0 to 100",
            "per_criterion_scores": {"criterion_name": "number from 0 to 100"},
            "rationale": "brief explanation",
            "failure_modes": ["short labels"],
            "recommended_fix": "brief actionable fix",
            "reference_example_ids": ["good example ids used"],
        }
    ]
}


DATASET_RESPONSE_SCHEMA = {
    "score": "number from 0 to 100",
    "per_criterion_scores": {"criterion_name": "number from 0 to 100"},
    "dataset_level_summary": "brief dataset-level summary",
    "top_failure_modes": ["short labels"],
    "recommended_fixes": ["actionable fixes"],
    "confidence": "brief note about coverage and uncertainty",
}


def build_row_batch_prompt(
    *,
    criteria_prompt: str,
    rows: list[NormalizedRow],
    references_by_row: dict[str, list[GoodExample]],
) -> str:
    reference_union: dict[str, GoodExample] = {}
    row_payloads: list[dict[str, Any]] = []
    for row in rows:
        refs = references_by_row.get(row.row_id, [])
        for ref in refs:
            reference_union[ref.id] = ref
        row_payloads.append(
            {
                "row_id": row.row_id,
                "input": clean_text(row.input, max_chars=1400),
                "context": clean_text(row.context, max_chars=2200),
                "target_assistant": clean_text(row.target_assistant, max_chars=1600),
                "messages": _compact_messages(row.messages),
                "reference_example_ids": [ref.id for ref in refs],
            }
        )

    return (
        "You are GPT-4.1 acting as a strict but fair ML evaluation judge for Learning Friend AI datasets.\n\n"
        f"{POSITIVE_REFERENCE_NOTICE}\n\n"
        "Written evaluation criteria, highest priority:\n"
        f"{criteria_prompt.strip()}\n\n"
        "Evaluate each target assistant response as a dataset row. Do not score by surface similarity alone. "
        "Reward behavior that follows the written criteria and the Learning Friend style: one clear question, "
        "small nudges before answers, gentle correction, source/context grounding, warm acceptance of correction, "
        "and natural friend tone without unsupported facts.\n\n"
        "Positive reference examples (all provided examples):\n"
        f"{json.dumps(compact_examples(list(reference_union.values())), ensure_ascii=False, indent=2)}\n\n"
        "Target rows to evaluate:\n"
        f"{json.dumps(row_payloads, ensure_ascii=False, indent=2)}\n\n"
        "Return valid JSON only. Use this exact top-level shape:\n"
        f"{json.dumps(ROW_BATCH_RESPONSE_SCHEMA, ensure_ascii=False, indent=2)}"
    )


def build_dataset_summary_prompt(
    *,
    criteria_prompt: str,
    target_name: str,
    evaluated_count: int,
    total_count: int,
    row_evaluations: list[RowEvaluation],
    references: list[GoodExample],
) -> str:
    failures = Counter()
    for evaluation in row_evaluations:
        failures.update(evaluation.failure_modes)
    low_rows = sorted(row_evaluations, key=lambda item: item.score)[:10]
    payload = {
        "target_name": target_name,
        "row_count_evaluated": evaluated_count,
        "total_count": total_count,
        "row_score_mean": _mean([row.score for row in row_evaluations]),
        "top_failure_modes_from_rows": failures.most_common(12),
        "low_score_rows": [
            {
                "row_id": row.row_id,
                "score": row.score,
                "failure_modes": row.failure_modes,
                "rationale": clean_text(row.rationale, max_chars=700),
                "recommended_fix": clean_text(row.recommended_fix, max_chars=500),
            }
            for row in low_rows
        ],
    }
    return (
        "You are GPT-4.1 acting as a dataset-level ML evaluation judge for Learning Friend AI.\n\n"
        f"{POSITIVE_REFERENCE_NOTICE}\n\n"
        "Written evaluation criteria, highest priority:\n"
        f"{criteria_prompt.strip()}\n\n"
        "Use the row-level evidence below to produce a dataset-level score and actionable summary. "
        "Do not inflate the score just because the positive references are good; the target dataset is what you score.\n\n"
        "Positive reference examples (all provided examples):\n"
        f"{json.dumps(compact_examples(references), ensure_ascii=False, indent=2)}\n\n"
        "Row-level evidence:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return valid JSON only. Use this exact top-level shape:\n"
        f"{json.dumps(DATASET_RESPONSE_SCHEMA, ensure_ascii=False, indent=2)}"
    )


def build_comparison_text(targets: list[TargetResult]) -> str:
    if len(targets) < 2:
        return ""
    ranking = sorted(targets, key=lambda target: target.overall_score, reverse=True)
    lines = ["Score ranking:"]
    for idx, target in enumerate(ranking, 1):
        lines.append(f"{idx}. {target.target_name}: {target.overall_score:.1f}/100")
    best = ranking[0]
    lines.append("")
    lines.append(f"Best target: {best.target_name}")
    common = Counter()
    for target in targets:
        common.update(target.top_failure_modes)
    if common:
        lines.append("Common failure modes: " + ", ".join(item for item, _count in common.most_common(8)))
    return "\n".join(lines)


def _compact_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    compacted = []
    for msg in messages[-6:]:
        role = clean_text(msg.get("role"), max_chars=30)
        content = clean_text(msg.get("content"), max_chars=900)
        if role and content:
            compacted.append({"role": role, "content": content})
    return compacted


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
