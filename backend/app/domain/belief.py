from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


class DiagnosisBelief(BaseModel):
    condition_id: str
    rank: int = Field(ge=1)
    probability: float = Field(ge=0.0, le=1.0)


class BeliefSubmission(BaseModel):
    diagnoses: List[DiagnosisBelief]
    overall_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("diagnoses")
    @classmethod
    def diagnoses_are_nonempty(cls, value: List[DiagnosisBelief]):
        if not value:
            raise ValueError("At least one diagnosis is required")
        return value

    @model_validator(mode="after")
    def diagnoses_are_unique_and_ranked(self):
        conditions = [item.condition_id for item in self.diagnoses]
        ranks = [item.rank for item in self.diagnoses]
        if len(conditions) != len(set(conditions)):
            raise ValueError("Diagnosis conditions must be unique")
        if len(ranks) != len(set(ranks)):
            raise ValueError("Diagnosis ranks must be unique")
        return self
