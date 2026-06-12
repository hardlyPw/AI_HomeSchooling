# Learning Friend Autorater

Learning Friend Autorater is a small desktop tool for evaluating model-output datasets against a written rubric. It is designed for internal review of Learning Friend style responses, especially whether responses are short, grounded, friendly, and focused on helping the learner think instead of giving away answers too early.

## Features

- Evaluates JSONL, JSON, and CSV datasets.
- Uses the OpenAI chat completions API.
- Lets the user enter an API key at runtime.
- Supports a configurable judge model.
- Loads positive reference examples from a local JSONL file.
- Saves evaluation results as JSON and CSV files.
- Shows previous evaluation results in the app.

## What Is Not Included

This repository intentionally does not include:

- API keys
- private datasets
- positive reference datasets
- evaluation result files
- build artifacts
- local machine paths

Put your own positive reference file at:

```text
evals/good_dataset_examples.jsonl
```

or choose another file from the app UI.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Required Inputs

1. Evaluation criteria prompt
2. OpenAI API key
3. Judge model name
4. Target dataset
5. Positive reference examples file

The API key is entered by the user and is not hard-coded in the source code.

## Positive Reference Examples

The positive reference file should be JSONL. Each line should contain one good response example.

Recommended fields:

```json
{
  "id": "example_001",
  "category": "one_question",
  "source": "manual",
  "input": "student message",
  "context": "optional context",
  "ideal_assistant": "short friendly response",
  "messages": [],
  "criteria_tags": ["one_question", "no_answer_leak"],
  "why_good": "why this is a good Learning Friend response",
  "watch_out_for": "common mistake to avoid"
}
```

The provided good examples are positive references, not training data and not an exhaustive rubric. Use them to calibrate style and policy, but score the target dataset against the written evaluation criteria.

## Target Dataset Formats

The app can read `.jsonl`, `.json`, and `.csv`.

Common target response fields:

- `target_assistant`
- `ideal_assistant`
- `assistant`
- `assistant_response`
- `model_output`
- `output`
- `response`
- `completion`
- `rewritten_assistant`

For chat-style rows, the app can also read `messages` and use the last assistant message as the response being evaluated.

## Result Files

Each run is saved under:

```text
results/<run_id>/
```

Generated files:

- `run_result.json`
- `summary.csv`
- `row_scores.csv`
- `criterion_scores.csv`
- `paired_comparison.csv`

Result files are ignored by git by default.
