"""Interactive terminal UI for PropShield.

A rich-powered text interface that lets you pick a risk level, scout the index
watchlist, review ranked setups, and execute trades — with a confirmation gate
before any order, and an extra gate before live orders.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from propshield.config import Config
from propshield.engine import ScanResult, TradingEngine
from propshield.models import Side, Signal, TradePlan

console = Console()


class Terminal:
    """Drives the engine via an interactive menu."""

    def __init__(self, engine: TradingEngine, config: Config, paper: bool):
        self.engine = engine
        self.config = config
        self.paper = paper
        self.risk_level = config.risk.default_level
        self.last_scan: list[ScanResult] = []

    # -- presentation helpers ------------------------------------------------
    @property
    def mode_label(self) -> str:
        if self.paper:
            return "PAPER (simulated)"
        return self.config.environment_name  # DEMO or LIVE

    def _mode_style(self) -> str:
        if self.paper:
            return "bold cyan"
        return "bold red" if self.config.live else "bold yellow"

    def header(self) -> None:
        try:
            acct = self.engine.account()
            acct_line = (
                f"Balance: {acct.balance:,.2f} {acct.currency}   "
                f"Equity: {acct.equity:,.2f}   "
                f"Open positions: {acct.open_positions}"
            )
        except Exception as exc:
            acct_line = f"[red]account unavailable: {exc}[/red]"

        body = Text()
        body.append("Mode: ", style="bold")
        body.append(self.mode_label + "\n", style=self._mode_style())
        body.append("Risk level: ", style="bold")
        body.append(
            f"{self.risk_level} "
            f"({self.config.risk.risk_pct(self.risk_level) * 100:.2f}% equity/trade)\n"
        )
        body.append(acct_line)
        console.print(Panel(body, title="PropShield — Indices Trading Bot",
                            border_style=self._mode_style()))

    # -- actions -------------------------------------------------------------
    def do_scan(self) -> None:
        console.print("[dim]Scouting watchlist…[/dim]")
        instruments = self.engine.resolve_watchlist()
        if not instruments:
            console.print(
                "[red]No watchlist instruments could be resolved on this "
                "broker. Check the watchlist symbols in config.[/red]"
            )
            return
        self.last_scan = self.engine.scan(instruments)
        self._render_scan(self.last_scan)

    def _render_scan(self, results: list[ScanResult]) -> None:
        table = Table(title="Scout results (ranked by conviction)")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Symbol", style="bold")
        table.add_column("Direction")
        table.add_column("Score", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("ATR", justify="right")
        table.add_column("Notes", style="dim")

        ranked = self.engine.rank(results)
        threshold = self.config.strategy.min_score
        for i, sig in enumerate(ranked, 1):
            side_style = "green" if sig.side is Side.BUY else "red"
            score_style = "bold green" if sig.score >= threshold else "yellow"
            table.add_row(
                str(i),
                sig.symbol,
                Text(sig.side.value.upper(), style=side_style),
                Text(f"{sig.score:.1f}", style=score_style),
                f"{sig.price:,.2f}",
                f"{sig.atr:,.2f}",
                ", ".join(sig.reasons[:3]),
            )

        # Instruments that produced no signal / errored.
        for r in results:
            if r.signal is None:
                note = r.error or "no setup / insufficient data"
                table.add_row("-", r.instrument.symbol, "—", "—", "—", "—", note)

        console.print(table)
        if not ranked:
            console.print("[yellow]No tradable signals this scan.[/yellow]")
        else:
            console.print(
                f"[dim]Minimum tradable score: {threshold:.0f}. "
                f"Top setup: {ranked[0]}.[/dim]"
            )

    def _select_signal(self) -> Optional[Signal]:
        if not self.last_scan:
            console.print("[yellow]Run a scan first (option 1).[/yellow]")
            return None
        ranked = self.engine.rank(self.last_scan)
        if not ranked:
            console.print("[yellow]No signals available to trade.[/yellow]")
            return None
        default = "1"
        choice = Prompt.ask(
            "Trade which ranked setup? (number, or 'b' for best above threshold)",
            default=default,
        )
        if choice.strip().lower() == "b":
            best = self.engine.best_signal(self.last_scan)
            if best is None:
                console.print(
                    "[yellow]No signal clears the minimum score threshold.[/yellow]"
                )
            return best
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ranked):
                return ranked[idx]
        except ValueError:
            pass
        console.print("[red]Invalid selection.[/red]")
        return None

    def _render_plan(self, plan: TradePlan) -> None:
        table = Table(title=f"Trade plan — {plan.symbol}", show_header=False)
        table.add_column("k", style="bold")
        table.add_column("v")
        side_style = "green" if plan.side is Side.BUY else "red"
        table.add_row("Direction", Text(plan.side.value.upper(), style=side_style))
        table.add_row("Score", f"{plan.signal.score:.1f}")
        table.add_row("Quantity", f"{plan.quantity}")
        table.add_row("Entry (ref)", f"{plan.entry_price:,.2f}")
        table.add_row("Stop loss", f"{plan.stop_loss:,.2f}")
        table.add_row("Take profit", f"{plan.take_profit:,.2f}")
        table.add_row(
            "Risk", f"{plan.risk_amount:,.2f} ({plan.risk_pct * 100:.2f}% equity)"
        )
        table.add_row(
            "Reward:Risk", f"{self.config.risk.reward_risk_ratio:.1f} : 1"
        )
        console.print(table)

    def do_trade(self) -> None:
        signal = self._select_signal()
        if signal is None:
            return
        try:
            plan = self.engine.plan(signal, self.risk_level)
        except ValueError as exc:
            console.print(f"[red]Cannot size trade: {exc}[/red]")
            return

        self._render_plan(plan)

        if not Confirm.ask("Place this order?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

        # Extra confirmation gate for live trading.
        if not self.paper and self.config.live:
            console.print(
                Panel(
                    Text(
                        "This is a LIVE order using real funds.",
                        style="bold red",
                    ),
                    border_style="red",
                )
            )
            phrase = Prompt.ask("Type 'LIVE' to confirm")
            if phrase.strip() != "LIVE":
                console.print("[dim]Live confirmation failed — cancelled.[/dim]")
                return

        try:
            order_id = self.engine.execute(plan)
            console.print(
                f"[bold green]Order placed.[/bold green] id={order_id} "
                f"{plan.side.value.upper()} {plan.quantity} {plan.symbol}"
            )
        except Exception as exc:
            console.print(f"[red]Order failed: {exc}[/red]")

    def do_positions(self) -> None:
        try:
            positions = self.engine.broker.get_positions()
        except Exception as exc:
            console.print(f"[red]Could not fetch positions: {exc}[/red]")
            return
        if not positions:
            console.print("[dim]No open positions.[/dim]")
            return
        table = Table(title="Open positions")
        for col in ("ID", "Symbol", "Side", "Qty", "Entry", "SL", "TP", "uPnL"):
            table.add_column(col)
        for p in positions:
            pnl_style = "green" if p.unrealized_pnl >= 0 else "red"
            table.add_row(
                p.position_id,
                p.symbol,
                p.side.value.upper(),
                f"{p.quantity}",
                f"{p.entry_price:,.2f}",
                f"{p.stop_loss:,.2f}" if p.stop_loss else "—",
                f"{p.take_profit:,.2f}" if p.take_profit else "—",
                Text(f"{p.unrealized_pnl:,.2f}", style=pnl_style),
            )
        console.print(table)

    def do_close(self) -> None:
        positions = self.engine.broker.get_positions()
        if not positions:
            console.print("[dim]No open positions to close.[/dim]")
            return
        self.do_positions()
        pid = Prompt.ask("Position ID to close (or 'c' to cancel)")
        if pid.strip().lower() == "c":
            return
        try:
            self.engine.broker.close_position(pid.strip())
            console.print(f"[green]Closed position {pid}.[/green]")
        except Exception as exc:
            console.print(f"[red]Close failed: {exc}[/red]")

    def do_risk(self) -> None:
        levels = self.engine.risk.levels()
        console.print(f"Available risk levels: {', '.join(levels)}")
        choice = Prompt.ask(
            "Select risk level", choices=levels, default=self.risk_level
        )
        self.risk_level = choice
        pct = self.config.risk.risk_pct(choice) * 100
        console.print(f"[green]Risk level set to {choice} ({pct:.2f}% per trade).[/green]")

    # -- main loop -----------------------------------------------------------
    MENU = (
        "[1] Scout indices    "
        "[2] Set risk level    "
        "[3] Trade a setup    "
        "[4] Positions    "
        "[5] Close position    "
        "[6] Refresh    "
        "[q] Quit"
    )

    def run(self) -> None:
        console.print(
            "[bold]Welcome to PropShield[/bold] — terminal indices trading bot."
        )
        while True:
            console.print()
            self.header()
            console.print(self.MENU)
            choice = Prompt.ask("Select", default="1").strip().lower()
            if choice == "1":
                self.do_scan()
            elif choice == "2":
                self.do_risk()
            elif choice == "3":
                self.do_trade()
            elif choice == "4":
                self.do_positions()
            elif choice == "5":
                self.do_close()
            elif choice == "6":
                continue  # header refresh happens at loop top
            elif choice in {"q", "quit", "exit"}:
                console.print("[dim]Goodbye.[/dim]")
                return
            else:
                console.print("[red]Unknown option.[/red]")
