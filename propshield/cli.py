"""Command-line entry point for PropShield."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from propshield.config import load_config
from propshield.factory import build_engine
from propshield.terminal import Terminal

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="propshield",
        description="PropShield — terminal indices trading bot for TradeLocker.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--paper",
        action="store_true",
        help="Run fully offline against the simulated paper broker (default if "
        "no credentials are configured).",
    )
    mode.add_argument(
        "--demo",
        action="store_true",
        help="Connect to the TradeLocker DEMO environment.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Connect to the TradeLocker LIVE environment (real funds).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a YAML config file (defaults to config/default.yaml).",
    )
    parser.add_argument(
        "--scan-once",
        action="store_true",
        help="Run a single scout scan, print the ranked table, and exit.",
    )
    return parser


def resolve_mode(args, config) -> bool:
    """Decide whether to use the paper broker. Updates config.live in place.

    Returns True for paper mode.
    """
    if args.paper:
        return True
    if args.live:
        config.live = True
        return False
    if args.demo:
        config.live = False
        return False
    # No explicit mode: use live broker only if credentials exist, else paper.
    if config.credentials.complete:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)

    paper = resolve_mode(args, config)

    if not paper and not config.credentials.complete:
        console.print(
            "[red]Cannot connect: TradeLocker credentials are not configured.[/red]\n"
            "Set TRADELOCKER_USERNAME / TRADELOCKER_PASSWORD / TRADELOCKER_SERVER "
            "(see .env.example), or run with --paper."
        )
        return 2

    try:
        engine = build_engine(config, paper=paper)
    except Exception as exc:
        console.print(f"[red]Failed to start: {exc}[/red]")
        return 1

    if args.scan_once:
        results = engine.scan()
        terminal = Terminal(engine, config, paper=paper)
        terminal.last_scan = results
        terminal._render_scan(results)
        return 0

    terminal = Terminal(engine, config, paper=paper)
    try:
        terminal.run()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Interrupted — exiting.[/dim]")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
