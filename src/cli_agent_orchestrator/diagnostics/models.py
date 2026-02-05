"""Diagnostics result models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiagnosticStepResult(BaseModel):
    name: str
    ok: bool
    billable: bool = False
    duration_ms: int = 0
    details: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DiagnosticResult(BaseModel):
    provider: str
    agent_profile: str
    mode: str
    allow_billing: bool
    ok: bool
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    steps: List[DiagnosticStepResult]

    def finalize(self) -> "DiagnosticResult":
        self.finished_at = datetime.utcnow()
        self.ok = all(step.ok for step in self.steps)
        return self
