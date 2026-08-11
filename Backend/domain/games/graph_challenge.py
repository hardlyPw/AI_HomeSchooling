from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
from uuid import uuid4

from domain.games.math_expression import FUNCTION_TARGETS, FunctionTarget, MathExpression


ROUND_COUNT = 3
ROUND_TIME_LIMIT_MS = 60_000
MAX_TIME_BONUS = 10.0
X_MIN = -6.0
X_MAX = 6.0
Y_MIN = -12.0
Y_MAX = 12.0


def expression_points(expression: MathExpression, *, step: float = 0.1) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    count = round((X_MAX - X_MIN) / step)
    for index in range(count + 1):
        x = X_MIN + index * step
        value = expression.evaluate(x)
        if value is not None and Y_MIN * 3 <= value <= Y_MAX * 3:
            points.append((round(x, 3), round(max(Y_MIN, min(Y_MAX, value)), 4)))
    return tuple(points)


def graph_similarity(target: MathExpression, guess: MathExpression) -> float:
    errors: list[float] = []
    missing = 0
    for index in range(97):
        x = X_MIN + index * (X_MAX - X_MIN) / 96
        target_value = target.evaluate(x)
        if target_value is None or not Y_MIN <= target_value <= Y_MAX:
            continue
        guess_value = guess.evaluate(x)
        if guess_value is None:
            missing += 1
            continue
        errors.append(min(abs(target_value - guess_value), Y_MAX - Y_MIN) / (Y_MAX - Y_MIN))
    if not errors:
        return 0.0
    mean_error = (sum(errors) + missing) / (len(errors) + missing)
    return round(max(0.0, 100.0 * (1.0 - 3.2 * mean_error)), 1)


def time_bonus(elapsed_ms: int) -> float:
    clamped = max(0, min(ROUND_TIME_LIMIT_MS, elapsed_ms))
    return round(MAX_TIME_BONUS * (1.0 - clamped / ROUND_TIME_LIMIT_MS), 1)


@dataclass(frozen=True)
class GraphChallengeAttempt:
    expression: str
    graph_score: float
    time_bonus: float
    score: float
    elapsed_ms: int


@dataclass
class GraphChallengeRound:
    number: int
    target: FunctionTarget
    attempt: GraphChallengeAttempt | None = None

    @property
    def completed(self) -> bool:
        return self.attempt is not None


@dataclass
class GraphChallengeSession:
    id: str
    user_id: str
    player_name: str
    rounds: list[GraphChallengeRound]
    current_round_index: int = 0
    completed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    @classmethod
    def create(cls, *, user_id: str, player_name: str, seed: int | str | None = None) -> GraphChallengeSession:
        session_id = uuid4().hex
        rng = random.Random(seed if seed is not None else session_id)
        families = rng.sample(sorted({target.family for target in FUNCTION_TARGETS}), k=ROUND_COUNT)
        targets = [rng.choice([target for target in FUNCTION_TARGETS if target.family == family]) for family in families]
        return cls(
            id=session_id,
            user_id=user_id,
            player_name=player_name,
            rounds=[GraphChallengeRound(index + 1, target) for index, target in enumerate(targets)],
        )

    @property
    def current_round(self) -> GraphChallengeRound:
        return self.rounds[self.current_round_index]

    @property
    def total_score(self) -> float:
        return round(sum(round_state.attempt.score for round_state in self.rounds if round_state.attempt), 1)
