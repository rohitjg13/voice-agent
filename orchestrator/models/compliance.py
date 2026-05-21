from dataclasses import dataclass


@dataclass
class ComplianceViolation:
    kind: str  # "banned_word" | "missing_disclosure"
    detail: str
