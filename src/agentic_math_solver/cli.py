from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import AppConfig
from .orchestrator import SwarmOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-math-solver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve = subparsers.add_parser("solve", help="Solve a single math problem locally")
    solve.add_argument("--problem", help="Problem text")
    solve.add_argument("--problem-file", help="Path to a text file containing the problem")

    subparsers.add_parser("serve", help="Launch the graphical chatbot UI")
    return parser


def _load_problem(args: argparse.Namespace) -> str:
    if args.problem:
        return args.problem
    if args.problem_file:
        return Path(args.problem_file).read_text(encoding="utf-8")
    return sys.stdin.read().strip()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = AppConfig.from_env()

    if args.command == "serve":
        from .web.app import launch_app

        print("Starting local web UI...")
        launch_app(config)
        return

    problem = _load_problem(args).strip()
    if not problem:
        raise SystemExit("No problem text provided.")

    solver = SwarmOrchestrator(config)
    result = solver.solve(problem)

    print(result.final_answer)
    if result.used_judge:
        print("Judge used")
    print(result.vote_counts)


if __name__ == "__main__":
    main()
