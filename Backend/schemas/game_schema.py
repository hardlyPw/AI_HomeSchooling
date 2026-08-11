from __future__ import annotations

from pydantic import BaseModel, Field


class GraphPoint(BaseModel):
    x: float
    y: float


class GraphFunctionRequest(BaseModel):
    coefficient: int
    base: float
    horizontal_shift: int
    vertical_shift: int


class StartGraphMatchRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=80)


class SubmitGraphAttemptRequest(GraphFunctionRequest):
    elapsed_ms: int = Field(default=0, ge=0, le=600_000)


class QuickChatRequest(BaseModel):
    chat: str


class GraphAttemptResponse(BaseModel):
    latex: str
    graph_score: float
    time_bonus: float
    score: float
    elapsed_ms: int


class GraphRoundResponse(BaseModel):
    number: int
    target_points: list[GraphPoint]
    attempts: list[GraphAttemptResponse]
    attempts_remaining: int
    completed: bool
    target_latex: str | None = None
    agent_latex: str | None = None
    agent_points: list[GraphPoint] = Field(default_factory=list)
    agent_graph_score: float | None = None
    agent_time_bonus: float | None = None
    agent_score: float | None = None
    agent_elapsed_ms: int | None = None
    winner: str | None = None


class QuickChatEventResponse(BaseModel):
    sender: str
    chat: str
    text: str


class GraphMatchResponse(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    agent_skill: str
    round_count: int
    current_round: GraphRoundResponse
    rounds: list[GraphRoundResponse]
    user_round_wins: int
    agent_round_wins: int
    user_total_score: float
    agent_total_score: float
    completed: bool
    overall_winner: str | None
    quick_chats: list[QuickChatEventResponse]
