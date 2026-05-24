"""Pydantic schemas for /onboarding endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class KYCRequest(BaseModel):
    answers: list[int] = Field(
        ...,
        min_length=5,
        max_length=5,
        description="Exactly 5 risk-questionnaire answers, each 1-5.",
    )
    terms_version: str = Field(..., min_length=1)

    @field_validator("answers")
    @classmethod
    def _each_answer_in_range(cls, v: list[int]) -> list[int]:
        for x in v:
            if not 1 <= x <= 5:
                raise ValueError("each answer must be between 1 and 5")
        return v


class KYCResponse(BaseModel):
    risk_tolerance: str
