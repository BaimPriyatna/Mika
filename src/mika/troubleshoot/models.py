from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HypothesisLikelihood(str, Enum):

    VERY_LIKELY = "very_likely"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNLIKELY = "unlikely"


class Hypothesis(BaseModel):

    model_config = ConfigDict(frozen=True)

    description: str = Field(description="What might be causing the problem")
    likelihood: HypothesisLikelihood = Field(description="How likely this cause is")
    evidence: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Observations supporting this hypothesis",
    )
    tests_performed: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tests that were run to evaluate this hypothesis",
    )


class DiagnosisResult(BaseModel):

    model_config = ConfigDict(frozen=True)

    problem_description: str = Field(description="The reported problem")
    router_identity: str = Field(description="Router being diagnosed")
    diagnosed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When diagnosis was performed",
    )
    
    hypotheses: tuple[Hypothesis, ...] = Field(
        default_factory=tuple,
        description="Potential causes, ranked by likelihood",
    )
    
    recommended_fixes: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Recommended actions to resolve the issue",
    )
    
    state_collected: dict[str, Any] = Field(
        default_factory=dict,
        description="Relevant router state that was collected",
    )

    @property
    def most_likely_cause(self) -> Hypothesis | None:
        if not self.hypotheses:
            return None
        return self.hypotheses[0]


class TroubleshootingSession(BaseModel):

    model_config = ConfigDict(frozen=False)

    session_id: str = Field(description="Unique session identifier")
    problem_description: str = Field(description="User-reported problem")
    router_identity: str = Field(description="Router being diagnosed")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    
    state_collected: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    tests_performed: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    
    completed: bool = Field(default=False)
    completed_at: datetime | None = Field(default=None)

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        self.hypotheses.append(hypothesis)

    def add_test(self, test_description: str) -> None:
        self.tests_performed.append(test_description)

    def add_fix(self, fix_description: str) -> None:
        self.recommended_fixes.append(fix_description)

    def complete(self) -> DiagnosisResult:
        self.completed = True
        self.completed_at = datetime.now(timezone.utc)
        
        sorted_hypotheses = sorted(
            self.hypotheses,
            key=lambda h: {
                HypothesisLikelihood.VERY_LIKELY: 0,
                HypothesisLikelihood.LIKELY: 1,
                HypothesisLikelihood.POSSIBLE: 2,
                HypothesisLikelihood.UNLIKELY: 3,
            }[h.likelihood],
        )
        
        return DiagnosisResult(
            problem_description=self.problem_description,
            router_identity=self.router_identity,
            diagnosed_at=self.completed_at or datetime.now(timezone.utc),
            hypotheses=tuple(sorted_hypotheses),
            recommended_fixes=tuple(self.recommended_fixes),
            state_collected=self.state_collected,
        )
