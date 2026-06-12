from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from autorater.core.api_client import JudgeApiClient
from autorater.core.loaders import load_dataset
from autorater.core.prompts import (
    DATASET_RESPONSE_SCHEMA,
    ROW_BATCH_RESPONSE_SCHEMA,
    build_dataset_summary_prompt,
    build_row_batch_prompt,
)
from autorater.core.references import load_good_examples
from autorater.core.schemas import (
    AutoraterRunResult,
    AutoraterSettings,
    ComparisonSummary,
    DatasetLevelEvaluation,
    LowScoreExample,
    RowEvaluation,
    TargetResult,
    TargetSpec,
)
from autorater.core.utils import clamp_score, clean_text, stable_hash


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
StopCallback = Callable[[], bool]


class Autorater:
    def __init__(
        self,
        *,
        criteria_prompt: str,
        api_url: str,
        api_key: str,
        good_examples_path: str,
        targets: list[TargetSpec],
        settings: AutoraterSettings,
        log: LogCallback | None = None,
        progress: ProgressCallback | None = None,
        should_stop: StopCallback | None = None,
    ):
        self.criteria_prompt = criteria_prompt.strip()
        self.api_url = api_url.strip()
        self.good_examples_path = str(Path(good_examples_path))
        self.targets = targets
        self.settings = settings
        self.log = log or (lambda _message: None)
        self.progress = progress or (lambda _current, _total: None)
        self.should_stop = should_stop or (lambda: False)
        self.client = JudgeApiClient(
            api_url=api_url,
            api_key=api_key,
            judge_model=settings.judge_model,
        )

    def run(self) -> AutoraterRunResult:
        if not self.criteria_prompt:
            raise ValueError("Evaluation criteria prompt is required.")
        if not self.targets:
            raise ValueError("At least one target dataset is required.")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + stable_hash(self.criteria_prompt, self.api_url, length=6)
        self.log("[INFO] Loading positive reference examples")
        examples = load_good_examples(self.good_examples_path)
        self.log(f"[INFO] Loaded {len(examples)} positive references")

        loaded_targets = []
        total_units = 0
        for target in self.targets:
            rows, detected_format = load_dataset(target.path, target.format)
            if not rows:
                raise ValueError(f"No rows found for target: {target.name}")
            rows_to_evaluate = self._rows_to_evaluate(rows)
            loaded_targets.append((target, rows, rows_to_evaluate, detected_format))
            total_units += len(rows_to_evaluate) + 1
            if len(rows_to_evaluate) < len(rows):
                self.log(
                    f"[INFO] Loaded {target.name}: {len(rows)} rows; "
                    f"evaluating random {len(rows_to_evaluate)} rows"
                )
            else:
                self.log(f"[INFO] Loaded {target.name}: {len(rows)} rows")
        current_units = 0

        target_results: list[TargetResult] = []
        for target, all_rows, rows_to_evaluate, detected_format in loaded_targets:
            if self.should_stop():
                self.log("[WARN] Evaluation stopped by user")
                break
            self.log(f"[INFO] Evaluating target: {target.name}")
            result, units_used = self._evaluate_target(
                target,
                examples,
                all_rows,
                rows_to_evaluate,
                detected_format,
                current_units,
                total_units,
            )
            current_units += units_used
            target_results.append(result)
            self.progress(min(current_units, total_units), total_units)

        comparison = build_comparison_summary(target_results)
        return AutoraterRunResult(
            run_id=run_id,
            criteria_prompt=self.criteria_prompt,
            positive_reference_count=len(examples),
            settings=self.settings,
            targets=target_results,
            comparison_summary=comparison,
        )

    def _rows_to_evaluate(self, rows):
        limit = self.settings.row_limit
        if limit is None or limit <= 0 or limit >= len(rows):
            return rows
        selected_indices = set(random.sample(range(len(rows)), limit))
        return [row for index, row in enumerate(rows) if index in selected_indices]

    def _evaluate_target(
        self,
        target: TargetSpec,
        examples,
        all_rows,
        rows,
        detected_format: str,
        current_units: int,
        total_units: int,
    ) -> tuple[TargetResult, int]:
        errors: list[str] = []
        if not rows:
            raise ValueError(f"No rows selected for target: {target.name}")
        missing_target = [row.row_id for row in rows if not row.target_assistant]
        if missing_target:
            errors.append(f"{len(missing_target)} rows had no target assistant text.")

        row_evaluations: list[RowEvaluation] = []
        units_used = 0
        stopped = False
        for batch in chunks(rows, self.settings.batch_size):
            if self.should_stop():
                stopped = True
                break
            references_by_row = {row.row_id: examples for row in batch}
            prompt = build_row_batch_prompt(
                criteria_prompt=self.criteria_prompt,
                rows=batch,
                references_by_row=references_by_row,
            )
            try:
                payload = self.client.call_json(
                    prompt,
                    response_schema=ROW_BATCH_RESPONSE_SCHEMA,
                    metadata={"target": target.name, "kind": "row_batch"},
                )
                batch_evaluations = normalize_row_evaluations(payload, batch, references_by_row)
            except Exception as exc:
                message = f"Row batch failed for {target.name}: {exc}"
                self.log(f"[ERROR] {message}")
                errors.append(message)
                batch_evaluations = [
                    RowEvaluation(
                        row_id=row.row_id,
                        score=0,
                        rationale="Evaluation call failed.",
                        failure_modes=["judge_api_error"],
                        recommended_fix="Retry after checking the OpenAI API key, network status, and response schema.",
                        reference_example_ids=[ref.id for ref in references_by_row.get(row.row_id, [])],
                        parse_error=str(exc),
                    )
                    for row in batch
                ]
            row_evaluations.extend(batch_evaluations)
            units_used += len(batch)
            current_units += len(batch)
            self.progress(min(current_units, total_units), total_units)
            self.log(f"[INFO] {target.name}: evaluated {len(row_evaluations)}/{len(rows)} selected rows")

        if stopped:
            errors.append("Evaluation stopped before all rows were evaluated.")

        dataset_eval = self._dataset_summary(target, examples, all_rows, row_evaluations)
        units_used += 1
        result = build_target_result(
            target=target,
            detected_format=detected_format,
            total_rows=len(all_rows),
            evaluated_rows=rows[: len(row_evaluations)] if stopped else rows,
            row_evaluations=row_evaluations,
            dataset_eval=dataset_eval,
            errors=errors,
        )
        self.log(f"[SUCCESS] {target.name}: {result.overall_score:.1f}/100")
        return result, units_used

    def _dataset_summary(
        self,
        target: TargetSpec,
        examples,
        all_rows,
        row_evaluations: list[RowEvaluation],
    ) -> DatasetLevelEvaluation:
        prompt = build_dataset_summary_prompt(
            criteria_prompt=self.criteria_prompt,
            target_name=target.name,
            evaluated_count=len(row_evaluations),
            total_count=len(all_rows),
            row_evaluations=row_evaluations,
            references=examples,
        )
        try:
            payload = self.client.call_json(
                prompt,
                response_schema=DATASET_RESPONSE_SCHEMA,
                metadata={"target": target.name, "kind": "dataset_summary"},
            )
            return normalize_dataset_evaluation(payload, row_evaluations)
        except Exception as exc:
            self.log(f"[ERROR] Dataset summary failed for {target.name}: {exc}")
            row_mean = mean([row.score for row in row_evaluations])
            failures = Counter()
            fixes: list[str] = []
            for row in row_evaluations:
                failures.update(row.failure_modes)
                if row.recommended_fix:
                    fixes.append(row.recommended_fix)
            return DatasetLevelEvaluation(
                score=row_mean,
                dataset_level_summary="Dataset-level judge call failed; score falls back to row-level mean.",
                top_failure_modes=[name for name, _count in failures.most_common(8)],
                recommended_fixes=dedupe_keep_order(fixes)[:8],
                parse_error=str(exc),
            )


def normalize_row_evaluations(
    payload: dict,
    rows,
    references_by_row,
) -> list[RowEvaluation]:
    raw_items = payload.get("row_evaluations")
    if not isinstance(raw_items, list):
        raise ValueError("Response missing row_evaluations list.")
    by_id = {str(item.get("row_id") or ""): item for item in raw_items if isinstance(item, dict)}
    evaluations: list[RowEvaluation] = []
    for row in rows:
        item = by_id.get(row.row_id)
        reference_ids = [ref.id for ref in references_by_row.get(row.row_id, [])]
        if not item:
            evaluations.append(
                RowEvaluation(
                    row_id=row.row_id,
                    score=0,
                    rationale="Judge response did not include this row.",
                    failure_modes=["missing_judge_row"],
                    recommended_fix="Retry this row or inspect judge API response.",
                    reference_example_ids=reference_ids,
                    parse_error="missing row evaluation",
                )
            )
            continue
        per_criterion = item.get("per_criterion_scores") if isinstance(item.get("per_criterion_scores"), dict) else {}
        evaluations.append(
            RowEvaluation(
                row_id=row.row_id,
                score=clamp_score(item.get("score")),
                per_criterion_scores={
                    clean_text(key): clamp_score(value)
                    for key, value in per_criterion.items()
                    if clean_text(key)
                },
                rationale=clean_text(item.get("rationale"), max_chars=1400),
                failure_modes=[clean_text(value) for value in item.get("failure_modes", []) if clean_text(value)]
                if isinstance(item.get("failure_modes"), list)
                else [],
                recommended_fix=clean_text(item.get("recommended_fix"), max_chars=1000),
                reference_example_ids=[
                    clean_text(value) for value in item.get("reference_example_ids", []) if clean_text(value)
                ]
                if isinstance(item.get("reference_example_ids"), list)
                else reference_ids,
            )
        )
    return evaluations


def normalize_dataset_evaluation(payload: dict, row_evaluations: list[RowEvaluation]) -> DatasetLevelEvaluation:
    per_criterion = payload.get("per_criterion_scores") if isinstance(payload.get("per_criterion_scores"), dict) else {}
    fallback_score = mean([row.score for row in row_evaluations])
    return DatasetLevelEvaluation(
        score=clamp_score(payload.get("score", fallback_score)),
        per_criterion_scores={
            clean_text(key): clamp_score(value)
            for key, value in per_criterion.items()
            if clean_text(key)
        },
        dataset_level_summary=clean_text(payload.get("dataset_level_summary"), max_chars=3000),
        top_failure_modes=[clean_text(value) for value in payload.get("top_failure_modes", []) if clean_text(value)]
        if isinstance(payload.get("top_failure_modes"), list)
        else [],
        recommended_fixes=[clean_text(value) for value in payload.get("recommended_fixes", []) if clean_text(value)]
        if isinstance(payload.get("recommended_fixes"), list)
        else [],
        confidence=clean_text(payload.get("confidence"), max_chars=1000),
    )


def build_target_result(
    *,
    target: TargetSpec,
    detected_format: str,
    total_rows: int,
    evaluated_rows,
    row_evaluations: list[RowEvaluation],
    dataset_eval: DatasetLevelEvaluation,
    errors: list[str],
) -> TargetResult:
    row_by_id = {row.row_id: row for row in evaluated_rows}
    row_mean = mean([row.score for row in row_evaluations])
    parse_error_count = sum(1 for row in row_evaluations if row.parse_error)
    penalty = min(10.0, parse_error_count * 2.0)
    overall = clamp_score(0.8 * row_mean + 0.2 * dataset_eval.score - penalty)

    failures = Counter()
    fixes: list[str] = []
    criteria_values: dict[str, list[float]] = defaultdict(list)
    for evaluation in row_evaluations:
        failures.update(evaluation.failure_modes)
        if evaluation.recommended_fix:
            fixes.append(evaluation.recommended_fix)
        for criterion, score in evaluation.per_criterion_scores.items():
            criteria_values[criterion].append(score)
    for criterion, score in dataset_eval.per_criterion_scores.items():
        criteria_values[criterion].append(score)
    per_criterion = {criterion: round(mean(values), 2) for criterion, values in sorted(criteria_values.items())}

    low_examples = []
    for evaluation in sorted(row_evaluations, key=lambda item: item.score)[:10]:
        source = row_by_id.get(evaluation.row_id)
        low_examples.append(
            LowScoreExample(
                row_id=evaluation.row_id,
                score=round(evaluation.score, 2),
                input=source.input if source else "",
                target_assistant=source.target_assistant if source else "",
                failure_modes=evaluation.failure_modes,
                recommended_fix=evaluation.recommended_fix,
                rationale=evaluation.rationale,
            )
        )

    top_failure_modes = dataset_eval.top_failure_modes or [name for name, _count in failures.most_common(10)]
    recommended_fixes = dataset_eval.recommended_fixes or dedupe_keep_order(fixes)[:10]
    return TargetResult(
        target_name=target.name,
        path=target.path,
        format=detected_format,
        row_count_total=total_rows,
        row_count_evaluated=len(row_evaluations),
        evaluated_row_ids=[row.row_id for row in evaluated_rows],
        overall_score=round(overall, 2),
        row_mean_score=round(row_mean, 2),
        dataset_level_score=round(dataset_eval.score, 2),
        per_criterion_scores=per_criterion,
        dataset_level_summary=dataset_eval.dataset_level_summary,
        top_failure_modes=top_failure_modes,
        low_score_examples=low_examples,
        recommended_fixes=recommended_fixes,
        row_level_scores=row_evaluations,
        errors=errors + ([dataset_eval.parse_error] if dataset_eval.parse_error else []),
    )


def build_comparison_summary(targets: list[TargetResult]) -> ComparisonSummary:
    if len(targets) < 2:
        return ComparisonSummary()
    ranking = [
        {
            "rank": idx,
            "target_name": target.target_name,
            "overall_score": target.overall_score,
            "row_count_evaluated": target.row_count_evaluated,
        }
        for idx, target in enumerate(sorted(targets, key=lambda item: item.overall_score, reverse=True), 1)
    ]
    best_target = ranking[0]["target_name"] if ranking else ""

    common = Counter()
    target_specific: list[dict[str, object]] = []
    for target in targets:
        common.update(target.top_failure_modes)
        target_specific.append(
            {
                "target_name": target.target_name,
                "top_failure_modes": target.top_failure_modes[:5],
                "lowest_score": target.low_score_examples[0].score if target.low_score_examples else None,
            }
        )

    paired = paired_score_deltas(targets)
    improvements = [item for item in paired if item["delta_best_minus_worst"] >= 10][:20]
    regressions = [item for item in paired if item["delta_best_minus_worst"] <= -10][:20]
    fix = ""
    if common:
        fix = f"Start by fixing the most common failure mode: {common.most_common(1)[0][0]}."
    return ComparisonSummary(
        score_ranking=ranking,
        best_target=str(best_target),
        paired_regressions=regressions,
        paired_improvements=improvements,
        common_failure_modes=[name for name, _count in common.most_common(10)],
        target_specific_risks=target_specific,
        recommended_next_dataset_fix=fix,
    )


def paired_score_deltas(targets: list[TargetResult]) -> list[dict[str, object]]:
    rows_by_target = {
        target.target_name: {row.row_id: row for row in target.row_level_scores}
        for target in targets
    }
    common_ids = set.intersection(*(set(rows.keys()) for rows in rows_by_target.values()))
    output: list[dict[str, object]] = []
    for row_id in sorted(common_ids):
        scores = {target_name: rows[row_id].score for target_name, rows in rows_by_target.items()}
        best_name = max(scores, key=scores.get)
        worst_name = min(scores, key=scores.get)
        output.append(
            {
                "row_id": row_id,
                "scores": scores,
                "best_target": best_name,
                "worst_target": worst_name,
                "delta_best_minus_worst": round(scores[best_name] - scores[worst_name], 2),
            }
        )
    output.sort(key=lambda item: abs(float(item["delta_best_minus_worst"])), reverse=True)
    return output


def chunks(values, size: int):
    size = max(1, int(size))
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output
