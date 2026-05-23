"""
CLI for the adversarial simulator.

Usage:
  python -m simulator.cli --all
  python -m simulator.cli --persona skeptical_office_manager
  python -m simulator.cli --persona compliance_tester --verbose

If VAPI_LLM_SECRET is set in .env, the runner attaches a matching Bearer header
automatically — production-parity testing works without extra flags.
"""

import argparse
import asyncio

from simulator.evaluator import format_report
from simulator.runner import load_personas, run_simulation


async def _run(args: argparse.Namespace) -> None:
    personas = load_personas()
    if args.persona:
        personas = [p for p in personas if p.name == args.persona]
        if not personas:
            print(f"No persona named '{args.persona}'")
            return

    results = []
    for p in personas:
        print(f"→ running {p.name} …")
        result = await run_simulation(p, max_turns=args.max_turns)
        results.append(result)
        if args.verbose:
            for turn in result.transcript:
                tag = "Agent " if turn["role"] == "assistant" else "Persona"
                print(f"  {tag}: {turn['content']}")
            print()

    print(format_report(results))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", help="Run a single persona by name")
    parser.add_argument("--all", action="store_true", help="Run all personas")
    parser.add_argument("--max-turns", type=int, default=14, help="Max conversation turns")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print full transcripts")
    args = parser.parse_args()

    if not args.persona and not args.all:
        parser.error("Specify --persona NAME or --all")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
