from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


class TargetSpec(BaseModel):
    name: str
    path: str
    format: str = "auto"


class AutoraterSettings(BaseModel):
    batch_size: int = 5
    row_limit: int | None = 80
    judge_model: str = "gpt-5.4-mini"


class NormalizedRow(BaseModel):
    row_id: str
    input: str = ""
    context: str = ""
    target_assistant: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class GoodExample(BaseModel):
    id: str
    category: str = ""
    source: str = ""
    input: str = ""
    context: str = ""
    ideal_assistant: str = ""
    criteria_tags: list[str] = Field(default_factory=list)
    why_good: str = ""
    watch_out_for: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class RowEvaluation(BaseModel):
    row_id: str
    score: float = 0.0
    per_criterion_scores: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    failure_modes: list[str] = Field(default_factory=list)
    recommended_fix: str = ""
    reference_example_ids: list[str] = Field(default_factory=list)
    parse_error: str = ""


class LowScoreExample(BaseModel):
    row_id: str
    score: float
    input: str = ""
    target_assistant: str = ""
    failure_modes: list[str] = Field(default_factory=list)
    recommended_fix: str = ""
    rationale: str = ""


class DatasetLevelEvaluation(BaseModel):
    score: float = 0.0
    per_criterion_scores: dict[str, float] = Field(default_factory=dict)
    dataset_level_summary: str = ""
    top_failure_modes: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    confidence: str = ""
    parse_error: str = ""


class TargetResult(BaseModel):
    target_name: str
    path: str
    format: str = ""
    row_count_total: int = 0
    row_count_evaluated: int = 0
    evaluated_row_ids: list[str] = Field(default_factory=list)
    overall_score: float = 0.0
    row_mean_score: float = 0.0
    dataset_level_score: float = 0.0
    per_criterion_scores: dict[str, float] = Field(default_factory=dict)
    dataset_level_summary: str = ""
    top_failure_modes: list[str] = Field(default_factory=list)
    low_score_examples: list[LowScoreExample] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    row_level_scores: list[RowEvaluation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ComparisonSummary(BaseModel):
    score_ranking: list[dict[str, Any]] = Field(default_factory=list)
    best_target: str = ""
    paired_regressions: list[dict[str, Any]] = Field(default_factory=list)
    paired_improvements: list[dict[str, Any]] = Field(default_factory=list)
    common_failure_modes: list[str] = Field(default_factory=list)
    target_specific_risks: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_dataset_fix: str = ""


class AutoraterRunResult(BaseModel):
    run_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    criteria_prompt: str
    api_provider: str = "OpenAI Chat Completions"
    positive_reference_set: str = "built-in positive reference set"
    positive_reference_count: int = 0
    settings: AutoraterSettings
    targets: list[TargetResult] = Field(default_factory=list)
    comparison_summary: ComparisonSummary = Field(default_factory=ComparisonSummary)
    output_dir: str = ""
