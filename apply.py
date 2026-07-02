#!/usr/bin/env python3
"""Apply Pilot CLI.

Usage:
  python apply.py <job_url>                 evaluate + dry-run form fill
  python apply.py <job_url> --submit        evaluate + fill + SUBMIT
  python apply.py <job_url> --no-fill       debate/decision only
  python apply.py --report                  application history
  python apply.py --status <url> <status>   record outcome (interview/rejected/offer)
"""
import asyncio
import re
import sys
from pathlib import Path

from apply_agent import memory
from apply_agent.orchestrator import evaluate_job, render_plan


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "job"


async def run(url: str, fill: bool, submit: bool) -> int:
    print(f"🎼 Apply Pilot — evaluating {url}\n")
    plan = await evaluate_job(url)
    print(render_plan(plan))

    if plan.cover_letter:
        out = Path("applications") / f"{_slug(plan.company + '-' + plan.title)}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(
            f"# {plan.title} @ {plan.company}\n\n{plan.url}\n\n"
            f"**Decision:** {plan.decision} (fit {plan.fit_score}/10)\n\n"
            f"## Cover letter\n\n{plan.cover_letter}\n\n"
            f"## Screener answers\n\n"
            + "\n".join(f"**{k}**: {v}\n" for k, v in plan.screener_answers.items()))
        print(f"\n📄 Materials saved: {out}")

    if plan.decision != "APPLY" or not fill:
        return 0

    print("\n🖊️  Filling the application form…")
    from apply_agent.form_filler import fill_application
    context = plan.cover_letter + "\n" + "\n".join(
        f"{k}: {v}" for k, v in plan.screener_answers.items())
    rep = await fill_application(url, plan_context=context, submit=submit)
    print("\n" + rep.summary())
    if rep.submitted:
        memory.set_status(url, "submitted")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--report":
        rows = memory.report()
        if not rows:
            print("No applications yet.")
            return 0
        for r in rows:
            print(f"{r['decision']:>5}  fit {r['fit_score']:>4}/10  "
                  f"[{r['status']}]  {r['title']} @ {r['company']}  {r['url']}")
        return 0
    if args[0] == "--status" and len(args) >= 3:
        memory.set_status(args[1], args[2])
        print(f"Recorded: {args[1]} → {args[2]}")
        return 0

    url = args[0]
    if not url.startswith("http"):
        print("First argument must be a job URL.")
        return 1
    return asyncio.run(run(url, fill="--no-fill" not in args, submit="--submit" in args))


if __name__ == "__main__":
    raise SystemExit(main())
