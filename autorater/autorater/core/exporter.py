from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from autorater.config import RESULTS_DIR
from autorater.core.evaluator import paired_score_deltas
from autorater.core.schemas import AutoraterRunResult, model_to_dict


def save_run_result(result: AutoraterRunResult, output_root: str | Path = RESULTS_DIR) -> Path:
    output_dir = Path(output_root) / result.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir = str(output_dir)
    payload = model_to_dict(result)
    (output_dir / "run_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary_csv(output_dir / "summary.csv", result)
    _write_row_scores_csv(output_dir / "row_scores.csv", result)
    _write_criterion_scores_csv(output_dir / "criterion_scores.csv", result)
    _write_paired_comparison_csv(output_dir / "paired_comparison.csv", result)
    return output_dir


def _write_summary_csv(path: Path, result: AutoraterRunResult) -> None:
    fields = [
        "target_name",
        "path",
        "format",
        "overall_score",
        "row_mean_score",
        "dataset_level_score",
        "row_count_total",
        "row_count_evaluated",
        "top_failure_modes",
        "recommended_fixes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for target in result.targets:
            writer.writerow(
                {
                    "target_name": target.target_name,
                    "path": target.path,
                    "format": target.format,
                    "overall_score": target.overall_score,
                    "row_mean_score": target.row_mean_score,
                    "dataset_level_score": target.dataset_level_score,
                    "row_count_total": target.row_count_total,
                    "row_count_evaluated": target.row_count_evaluated,
                    "top_failure_modes": "; ".join(target.top_failure_modes),
                    "recommended_fixes": "; ".join(target.recommended_fixes),
                }
            )


def _write_row_scores_csv(path: Path, result: AutoraterRunResult) -> None:
    fields = [
        "target_name",
        "row_id",
        "score",
        "failure_modes",
        "recommended_fix",
        "rationale",
        "reference_example_ids",
        "parse_error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for target in result.targets:
            for row in target.row_level_scores:
                writer.writerow(
                    {
                        "target_name": target.target_name,
                        "row_id": row.row_id,
                        "score": row.score,
                        "failure_modes": "; ".join(row.failure_modes),
                        "recommended_fix": row.recommended_fix,
                        "rationale": row.rationale,
                        "reference_example_ids": "; ".join(row.reference_example_ids),
                        "parse_error": row.parse_error,
                    }
                )


def _write_criterion_scores_csv(path: Path, result: AutoraterRunResult) -> None:
    fields = ["target_name", "criterion", "score"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for target in result.targets:
            for criterion, score in target.per_criterion_scores.items():
                writer.writerow(
                    {
                        "target_name": target.target_name,
                        "criterion": criterion,
                        "score": score,
                    }
                )


def _write_paired_comparison_csv(path: Path, result: AutoraterRunResult) -> None:
    fields = ["row_id", "best_target", "worst_target", "delta_best_minus_worst", "scores_json"]
    rows: list[dict[str, Any]] = paired_score_deltas(result.targets) if len(result.targets) >= 2 else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "row_id": row["row_id"],
                    "best_target": row["best_target"],
                    "worst_target": row["worst_target"],
                    "delta_best_minus_worst": row["delta_best_minus_worst"],
                    "scores_json": json.dumps(row["scores"], ensure_ascii=False),
                }
            )

