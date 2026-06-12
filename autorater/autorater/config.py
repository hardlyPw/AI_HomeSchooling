from __future__ import annotations

from pathlib import Path


APP_TITLE = "Learning Friend Autorater"
BASE_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = BASE_DIR / "results"
DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_GOOD_EXAMPLES_PATH = BASE_DIR / "evals" / "good_dataset_examples.jsonl"

DEFAULT_BATCH_SIZE = 5
DEFAULT_ROW_LIMIT = 80
DEFAULT_JUDGE_MODEL = "gpt-5.4-mini"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
