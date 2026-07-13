"""
Layer 7 (Debate Engine) + Layer 8 (Judge) + Layer 12 (Confidence Score)
"""
import asyncio
import json
import re
from dataclasses import dataclass, field
from . import providers as p
from .agents import AgentResult, AGENT_MAP
from .critics import Critique


# ── Debate Engine ─────────────────────────────────────────────────────────────

@dataclass
class DebateResult:
    answers:     list[AgentResult]
    rounds:      int
    stable:      bool


def _answers_stable(old: list[AgentResult], new_texts: list[str], threshold: float = 0.85) -> bool:
    """Check if debate has converged (answers barely changed)."""
    for old_r, new_t in zip(old, new_texts):
        old_words = set(old_r.answer.lower().split())
        new_words = set(new_t.lower().split())
        if not old_words:
            continue
        overlap = len(old_words & new_words) / max(len(old_words), len(new_words))
        if overlap < threshold:
            return False
    return True


async def run_debate(
    task: str,
    results: list[AgentResult],
    critique_summary: str,
    max_rounds: int = 5,
) -> DebateResult:
    """
    Each agent sees all other agents' answers + critique → revises.
    Stops when stable or max_rounds reached.
    """
    if len(results) <= 1:
        return DebateResult(answers=results, rounds=0, stable=True)

    current = results
    for round_num in range(max_rounds):
        revision_tasks = []
        for i, res in enumerate(current):
            agent = AGENT_MAP.get(res.agent)
            if not agent:
                continue
            others = [r.answer for j, r in enumerate(current) if j != i]
            revision_tasks.append(
                _revise_with_critique(agent, task, res.answer, others, critique_summary)
            )

        new_texts = await asyncio.gather(*revision_tasks)
        if not new_texts:
            break

        stable = _answers_stable(current, new_texts)
        for i, new_text in enumerate(new_texts):
            if i < len(current):
                current[i] = AgentResult(
                    agent=current[i].agent,
                    answer=new_text,
                    provider=current[i].provider,
                )

        if stable:
            return DebateResult(answers=current, rounds=round_num + 1, stable=True)

    return DebateResult(answers=current, rounds=max_rounds, stable=False)


async def _revise_with_critique(agent, task: str, my_answer: str,
                                 others: list[str], critique: str) -> str:
    others_text = "\n\n".join(f"--- Peer {i+1} ---\n{a[:400]}" for i, a in enumerate(others))
    return await p.think(
        prompt=(
            f"TASK: {task}\n\n"
            f"YOUR ANSWER:\n{my_answer[:700]}\n\n"
            f"CRITIQUES FROM REVIEW TEAM:\n{critique[:600]}\n\n"
            f"PEER ANSWERS:\n{others_text[:600]}\n\n"
            "Revise your answer to address the critiques and incorporate the best peer insights. "
            "Do NOT copy peers blindly — only adopt improvements. "
            "Reply with ONLY the revised answer:"
        ),
        system=agent._system(),
        max_tokens=agent._max_tokens(),
        prefer=agent.provider,
    )


# ── Judge ─────────────────────────────────────────────────────────────────────

METRICS = [
    ("accuracy",             0.20),
    ("logic",                0.15),
    ("evidence",             0.15),
    ("completeness",         0.10),
    ("consistency",          0.10),
    ("clarity",              0.10),
    ("novelty",              0.05),
    ("confidence",           0.05),
    ("risk",                 0.05),  # inverted: lower risk = higher score
    ("hallucination_risk",   0.05),  # inverted
]


@dataclass
class JudgeScore:
    agent:    str
    scores:   dict[str, int]   # metric → 0-100
    total:    float
    verdict:  str              # "winner" | "runner-up" | "rejected"


@dataclass
class JudgeResult:
    winner:       AgentResult
    all_scores:   list[JudgeScore]
    best_score:   float
    explanation:  str


async def judge(task: str, answers: list[AgentResult], critiques: list[Critique]) -> JudgeResult:
    """Score all answers and pick the winner."""
    scored = await asyncio.gather(*[
        _score_one(task, r, critiques) for r in answers
    ])

    # Best total weighted score
    best = max(scored, key=lambda s: s.total)
    winner_result = answers[scored.index(best)]

    # Mark verdicts
    for s in scored:
        s.verdict = "winner" if s is best else ("runner-up" if s.total >= best.total * 0.9 else "rejected")

    explanation = await p.think(
        prompt=(
            f"Task: {task}\n\n"
            f"Winner agent: {best.agent} (score: {best.total:.1f}/100)\n"
            f"Top scores: {json.dumps({k: v for k, v in best.scores.items()}, indent=2)}\n\n"
            "In one sentence, explain WHY this answer won:"
        ),
        system="You are a judge. Explain your decision concisely.",
        max_tokens=100,
        prefer="groq",
    )

    return JudgeResult(
        winner=winner_result,
        all_scores=scored,
        best_score=best.total,
        explanation=explanation,
    )


async def _score_one(task: str, result: AgentResult, critiques: list[Critique]) -> JudgeScore:
    critique_text = "\n".join(
        f"{c.reviewer}: {', '.join(c.issues[:1])}" for c in critiques if c.issues
    ) or "No major issues found."

    raw = await p.think(
        prompt=(
            f"TASK: {task}\n\n"
            f"ANSWER:\n{result.answer[:800]}\n\n"
            f"CRITIQUES:\n{critique_text[:400]}\n\n"
            "Score this answer on each metric (0-100). Reply ONLY with JSON:\n"
            '{"accuracy":X,"logic":X,"evidence":X,"completeness":X,'
            '"consistency":X,"clarity":X,"novelty":X,"confidence":X,'
            '"risk":X,"hallucination_risk":X}'
        ),
        system="You are a rigorous judge. Score objectively. No extra text.",
        max_tokens=150,
        prefer="groq",
    )

    try:
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        scores = json.loads(m.group()) if m else {}
    except Exception:
        scores = {k: 50 for k, _ in METRICS}

    # Ensure all metrics present, clamp 0-100
    for k, _ in METRICS:
        scores[k] = max(0, min(100, int(scores.get(k, 50))))

    # Invert risk scores (lower risk = better score)
    for inv in ("risk", "hallucination_risk"):
        scores[inv] = 100 - scores[inv]

    # Weighted total
    total = sum(scores.get(k, 50) * w for k, w in METRICS)

    # Penalty from critics
    max_penalty = max((c.score for c in critiques), default=0)
    total = max(0, total - max_penalty * 0.3)

    return JudgeScore(agent=result.agent, scores=scores, total=round(total, 1), verdict="")


# ── Confidence Score ──────────────────────────────────────────────────────────

def compute_confidence(
    judge_score: float,
    critiques: list[Critique],
    num_agents: int,
    has_search: bool,
) -> tuple[int, str]:
    """Returns (0-100 confidence, reason string).

    NOTE: _score_one() already applies critic penalty to the judge score via
    max_penalty * 0.3, so we do NOT subtract again here — that caused the
    double-penalty bug that produced 3% confidence.
    """
    base = judge_score  # already critic-adjusted by the judge

    # Bonus for multi-agent agreement and web-grounded search
    if num_agents >= 3:
        base += 5
    if has_search:
        base += 5

    # Enforce a sensible floor: even a bad answer gets 20%
    confidence = max(20, min(100, round(base)))

    # Reason string
    rejections = sum(1 for c in critiques if c.verdict == "reject")
    verifiers = []
    if num_agents >= 2: verifiers.append(f"{num_agents} agents")
    if has_search:       verifiers.append("web search")
    if rejections == 0:  verifiers.append("critics passed")

    reason = f"Verified by: {', '.join(verifiers)}" if verifiers else "Single-agent estimate"
    return confidence, reason
