"""Decision model: what a pipeline stage concludes about an event."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Verdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"
    ESCALATE = "escalate"


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    reason: str
    # Rule that produced the decision; None only for built-in defaults.
    rule_id: str | None = None
    # Replacement payload; required for MODIFY, forbidden otherwise.
    patched_payload: dict[str, Any] | None = None
    # Taint labels to add to the session as a consequence of this decision.
    add_taint: frozenset[str] = Field(default_factory=frozenset)

    @model_validator(mode="after")
    def _check_patch(self) -> Self:
        if self.verdict is Verdict.MODIFY and self.patched_payload is None:
            raise ValueError("MODIFY decisions require patched_payload")
        if self.verdict is not Verdict.MODIFY and self.patched_payload is not None:
            raise ValueError("patched_payload is only valid for MODIFY decisions")
        return self

    @classmethod
    def allow(cls, reason: str, rule_id: str | None = None) -> Self:
        return cls(verdict=Verdict.ALLOW, reason=reason, rule_id=rule_id)

    @classmethod
    def deny(cls, reason: str, rule_id: str | None = None) -> Self:
        return cls(verdict=Verdict.DENY, reason=reason, rule_id=rule_id)

    @classmethod
    def modify(
        cls, patched_payload: dict[str, Any], reason: str, rule_id: str | None = None
    ) -> Self:
        return cls(
            verdict=Verdict.MODIFY, reason=reason, rule_id=rule_id, patched_payload=patched_payload
        )

    @classmethod
    def escalate(cls, reason: str, rule_id: str | None = None) -> Self:
        return cls(verdict=Verdict.ESCALATE, reason=reason, rule_id=rule_id)
