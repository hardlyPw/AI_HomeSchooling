from __future__ import annotations

from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    requested_name: str = Field(min_length=1, max_length=40)
    relationship: str = Field(min_length=1, max_length=300)
    personality: str = Field(min_length=1, max_length=800)
    speech_style: str = Field(min_length=1, max_length=500)
    interests: str = Field(min_length=1, max_length=500)
    reaction_style: str = Field(default="", max_length=800)
    background: str = Field(default="", max_length=1200)
    avoidances: str = Field(default="", max_length=800)
    dialogue_examples: str = Field(default="", max_length=1200)
    additional_description: str = Field(default="", max_length=1200)


class AgentSummary(BaseModel):
    id: str
    type: str
    name: str
    description: str
    initial_affinity: int
    game_skill_tier: str
    capabilities: list[str]
    is_builtin: bool = False


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]
