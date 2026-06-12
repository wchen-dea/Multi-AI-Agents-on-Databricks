"""
Multi-Specialist Claude Agent
==============================
A supervisor + specialist multi-agent system with:
  - Shared memory layer   — agents read/write named artifacts across the session
  - Message bus           — agents send typed messages to each other
  - Peer review / feedback loop — supervisor asks Specialist B to critique A's work,
                                   then asks A to revise

Specialists:
  frontend, backend, ml_engineer, ai_engineer, fullstack, data_engineer, data_scientist

Usage:
    uv run multi-ai-agent --task "build a product recommendation system"
    uv run multi-ai-agent --task "set up an A/B test for our checkout flow" --project ./output
    uv run multi-ai-agent --task "create a RAG chatbot with FastAPI backend" --quiet
    uv run multi-ai-agent --task "build a churn prediction model" --show-memory --show-messages
    uv run multi-ai-agent --task "build a churn prediction model" --implementation langgraph
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .runtime_factory import build_runtime, config_from_env

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

LOGGER = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║         MULTI-SPECIALIST CLAUDE AGENT                           ║
╚══════════════════════════════════════════════════════════════════╝
  Task    : {task}
  Project : {project}
"""


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format=LOG_FORMAT,
        force=True,
    )


def parse_args() -> argparse.Namespace:
    default_workers = _env_int("SUPERVISOR_MAX_WORKERS", 4)
    default_impl = os.getenv("AI_APP_IMPLEMENTATION", "classic")
    p = argparse.ArgumentParser(
        description="Supervisor + specialist Claude agents with memory and messaging.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--task", required=True, help="High-level engineering task.")
    p.add_argument("--project", default="./output", metavar="PATH",
                   help="Directory where agents write files (default: ./output).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress intermediate tool logs.")
    p.add_argument("--workers", type=int, default=default_workers, metavar="N",
                   help=f"Max parallel specialist threads (default: {default_workers}).")
    p.add_argument(
        "--implementation",
        choices=["classic", "langgraph"],
        default=default_impl,
        help=f"Orchestration implementation to use (default: {default_impl}).",
    )
    p.add_argument("--show-memory", action="store_true",
                   help="Print shared memory snapshot in the final report.")
    p.add_argument("--show-messages", action="store_true",
                   help="Print full inter-agent message log in the final report.")
    p.add_argument("--reset-memory", action="store_true",
                   help="Clear shared memory and message bus before running.")
    return p.parse_args()


def print_report(result, show_memory: bool = False, show_messages: bool = False) -> None:
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + "  FINAL REPORT".center(68) + "║")
    print("╚" + "═" * 68 + "╝\n")
    print(result.final_output)

    if result.total_files:
        print("\n" + "─" * 70)
        print("Files written:")
        for f in sorted(set(result.total_files)):
            print(f"  {f}")

    if result.specialist_results:
        print("\n" + "─" * 70)
        print("Specialists invoked:")
        for r in result.specialist_results:
            status = "✓" if r.success else "✗"
            mem = f"  [{', '.join(r.memory_keys_written[:3])}]" if r.memory_keys_written else ""
            msg = f"  →{len(r.messages_sent)} msgs" if r.messages_sent else ""
            print(f"  {status} {r.specialist:15s}  {r.task[:55]}{mem}{msg}")

    if show_memory and result.memory_snapshot:
        print("\n" + "─" * 70)
        print("Shared memory snapshot:")
        for k, v in sorted(result.memory_snapshot.items()):
            snippet = str(v).replace("\n", " ")[:80]
            print(f"  {k}: {snippet}…" if len(str(v)) > 80 else f"  {k}: {v}")

    if show_messages and result.message_log:
        print("\n" + "─" * 70)
        print("Inter-agent message log:")
        for m in result.message_log:
            print(f"  #{m['id']:3d} {m['from']:15s} → {m['to']:15s}  [{m['type']:8s}]  {m['subject'][:50]}")

    print("\n" + "─" * 70)


def main() -> None:
    args = parse_args()
    configure_logging(verbose=not args.quiet)

    project = Path(args.project)

    if not args.quiet:
        print(BANNER.format(task=args.task, project=project))

    config = config_from_env(
        project_root=str(project),
        implementation=args.implementation,
        max_workers=args.workers,
        verbose=not args.quiet,
    )
    try:
        runtime = build_runtime(config)
    except ValueError as exc:
        LOGGER.error(str(exc))
        sys.exit(1)

    supervisor = runtime.supervisor

    if args.reset_memory:
        supervisor.memory.clear()
        supervisor.bus.clear()
        LOGGER.info("Cleared shared memory and message bus.")

    result = supervisor.run(task=args.task)
    print_report(result, show_memory=args.show_memory, show_messages=args.show_messages)


if __name__ == "__main__":
    main()
