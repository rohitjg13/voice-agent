"""Aggregate metrics across a set of simulator runs."""

from dataclasses import dataclass

from simulator.runner import SimResult


@dataclass
class Metrics:
    total: int
    booked: int
    book_rate: float
    avg_turns: float
    violations_total: int
    violations_by_persona: dict[str, list[str]]


def aggregate(results: list[SimResult]) -> Metrics:
    if not results:
        return Metrics(0, 0, 0.0, 0.0, 0, {})

    booked = sum(1 for r in results if r.reached_schedule)
    avg_turns = sum(r.turn_count for r in results) / len(results)
    violations_by_persona = {r.persona: r.compliance_violations for r in results if r.compliance_violations}
    violations_total = sum(len(v) for v in violations_by_persona.values())

    return Metrics(
        total=len(results),
        booked=booked,
        book_rate=booked / len(results),
        avg_turns=avg_turns,
        violations_total=violations_total,
        violations_by_persona=violations_by_persona,
    )


def format_report(results: list[SimResult]) -> str:
    metrics = aggregate(results)
    lines = [
        "═══ Simulator Report ═══",
        f"Personas run:        {metrics.total}",
        f"Demos booked:        {metrics.booked} ({metrics.book_rate:.0%})",
        f"Avg turns per call:  {metrics.avg_turns:.1f}",
        f"Compliance issues:   {metrics.violations_total}",
        "",
        "Per-persona breakdown:",
    ]
    for r in results:
        outcome = "✓ booked" if r.reached_schedule else "✗ no book"
        viol = f" — {len(r.compliance_violations)} violations" if r.compliance_violations else ""
        lines.append(f"  {r.persona:35} {outcome:10}  turns={r.turn_count}{viol}")
    return "\n".join(lines)
