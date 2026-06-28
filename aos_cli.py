"""
AOS CLI — run with: python aos_cli.py

Interactive terminal interface for the AI Operating System.
"""
import asyncio
import sys
import subprocess

# Auto-install deps
PKGS = ["aiohttp", "beautifulsoup4", "python-dotenv", "rich"]
for pkg in PKGS:
    try: __import__(pkg.replace("-","_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from aos.pipeline import AOS
from aos.config import AOSConfig as C

console = Console()


def print_response(resp, question: str):
    # Main answer
    console.print(Markdown(resp.answer))

    # Metadata table
    t = Table(show_header=False, box=None, padding=(0,1))
    t.add_column(style="dim")
    t.add_column(style="bold")

    bar = "█" * (resp.confidence // 10) + "░" * (10 - resp.confidence // 10)
    t.add_row("Confidence", f"{resp.confidence}% {bar}")
    t.add_row("", resp.confidence_reason)
    t.add_row("Task type", resp.task_type)
    t.add_row("Agents", ", ".join(resp.agents_used))
    t.add_row("Debate rounds", str(resp.debate_rounds))
    t.add_row("Critics", "✅ Passed" if resp.critics_passed else "⚠️ Issues found")
    t.add_row("Time", f"{resp.elapsed_ms}ms")
    if resp.sources:
        t.add_row("Sources", "\n".join(f"• {s[:60]}" for s in resp.sources[:3]))

    console.print(Panel(t, title="[dim]AOS Metadata[/dim]", border_style="dim"))


async def main():
    console.print(Panel(
        "[bold magenta]🧠 AOS — AI Operating System[/bold magenta]\n\n"
        f"[white]Providers: {', '.join(C.available_providers())}\n"
        "Layers: Orchestrator → Agents → Critics → Debate → Judge → Writer\n\n"
        "Type your question. Type [bold]feedback y/n[/bold] after any answer.\n"
        "Type [bold]clear[/bold] to reset context. [bold]quit[/bold] to exit.[/white]",
        border_style="magenta",
    ))

    aos = AOS()
    last_response_id = None

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            break

        if user_input.lower() == "clear":
            aos.memory.clear_short_term()
            console.print("[dim]Context cleared.[/dim]")
            continue

        if user_input.lower().startswith("feedback ") and last_response_id:
            useful = user_input.lower().endswith("y") or "yes" in user_input.lower()
            aos.record_feedback(last_response_id, useful)
            console.print(f"[dim]Feedback recorded ({'👍' if useful else '👎'}) — system will improve.[/dim]")
            continue

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold magenta]AOS thinking...[/bold magenta]"),
            console=console,
            transient=True,
        ) as prog:
            prog.add_task("", total=None)
            try:
                resp = await aos.process(user_input)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue

        console.print("\n[bold green]AOS:[/bold green]")
        print_response(resp, user_input)
        last_response_id = resp.response_id
        console.print("[dim]Type 'feedback y' (useful) or 'feedback n' (not useful)[/dim]")

    aos.close()
    console.print("[yellow]AOS offline.[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
