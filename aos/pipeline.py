"""
AOS Pipeline — all 14 layers wired together.

Flow:
  Input → Memory → Route → Agents (parallel) → Critics (parallel)
       → Debate (up to 5 rounds) → Fact Check → Judge → Confidence
       → Final Writer (Claude) → Memory Update → Output
"""
import asyncio
import time
from dataclasses import dataclass, field
from . import providers as p
from .config import AOSConfig as C
from .router import classify, RouteResult, TaskType
from .agents import run_agents_parallel, AgentResult
from .critics import run_all_critics, summarise_critiques, Critique
from .judge import run_debate, judge as run_judge, compute_confidence
from .memory import Memory


@dataclass
class AOSResponse:
    answer:      str
    confidence:  int
    confidence_reason: str
    task_type:   str
    agents_used: list[str]
    debate_rounds: int
    critics_passed: bool
    sources:     list[str] = field(default_factory=list)
    response_id: int = 0
    elapsed_ms:  int = 0


class AOS:
    """AI Operating System — the main entry point."""

    def __init__(self):
        self.memory = Memory()
        self.memory.connect()

    async def process(self, user_input: str, image_url: str = "") -> AOSResponse:
        t0 = time.time()

        # ── Layer 2: Orchestrator checks for simple/trivial queries ───────────
        if self._is_trivial(user_input):
            answer = await p.call_claude(user_input, "You are a helpful assistant.", 400)
            confidence, reason = 90, "Simple query — direct answer"
            rid = self.memory.store_response(user_input, answer, confidence)
            self.memory.add_turn("user", user_input)
            self.memory.add_turn("assistant", answer)
            return AOSResponse(
                answer=answer, confidence=confidence, confidence_reason=reason,
                task_type="conversation", agents_used=["claude"],
                debate_rounds=0, critics_passed=True, response_id=rid,
                elapsed_ms=int((time.time()-t0)*1000),
            )

        # ── Layer 10: Memory retrieval ────────────────────────────────────────
        context = self.memory.get_context(max_turns=4)
        past_qa = self.memory.get_recent_qa(limit=2)
        mem_hits = self.memory.retrieve(user_input, limit=3)
        mem_context = "\n".join(f"[Memory] {m.key}: {m.value[:150]}" for m in mem_hits)
        full_context = "\n".join(filter(None, [context, past_qa, mem_context]))

        # ── Layer 3: Task Router ──────────────────────────────────────────────
        route: RouteResult = classify(user_input)

        # ── Layer 4: Parallel web search (if needed) ──────────────────────────
        search_results = []
        if route.needs_search:
            search_results = await p.search(user_input, num=5)
            if search_results:
                for r in search_results[:3]:
                    self.memory.store("search", r.get("title",""), r.get("snippet",""))

        # ── Layer 4: Specialist Agents (all run in parallel) ──────────────────
        agent_results: list[AgentResult] = await run_agents_parallel(
            route.agents, user_input, full_context, search_results
        )
        all_sources = []
        for r in agent_results:
            all_sources.extend(r.sources)

        # ── Layer 5: Critical Thinking Team (parallel on best answer) ─────────
        # Run critics on the synthesized agent answers
        combined_for_critics = "\n\n".join(
            f"[{r.agent.upper()}]\n{r.answer[:500]}" for r in agent_results
        )
        critiques: list[Critique] = await run_all_critics(user_input, combined_for_critics)
        critique_summary = summarise_critiques(critiques)

        # ── Layer 6: Fact Verification ────────────────────────────────────────
        if route.needs_search and search_results:
            fact_check_note = await self._fact_check(user_input, combined_for_critics, search_results)
        else:
            fact_check_note = ""

        # ── Layer 7: Debate Engine ────────────────────────────────────────────
        critics_passed = all(c.verdict != "reject" for c in critiques)

        if route.needs_debate and len(agent_results) > 1:
            debate_result = await run_debate(
                task=user_input,
                results=agent_results,
                critique_summary=critique_summary + ("\n" + fact_check_note if fact_check_note else ""),
                max_rounds=C.MAX_DEBATE_ROUNDS,
            )
            final_agents = debate_result.answers
            debate_rounds = debate_result.rounds
        else:
            final_agents = agent_results
            debate_rounds = 0

        # ── Layer 8: Judge ────────────────────────────────────────────────────
        judge_result = await run_judge(user_input, final_agents, critiques)

        # ── Layer 12: Confidence Score ────────────────────────────────────────
        confidence, conf_reason = compute_confidence(
            judge_score=judge_result.best_score,
            critiques=critiques,
            num_agents=len(agent_results),
            has_search=bool(search_results),
        )

        # ── Layer 9: Final Writer (Claude rewrites winner) ────────────────────
        final_answer = await self._final_write(
            user_input=user_input,
            winner=judge_result.winner.answer,
            critique_summary=critique_summary,
            fact_note=fact_check_note,
            confidence=confidence,
            sources=list(dict.fromkeys(all_sources))[:5],
        )

        # ── Layer 10: Memory Update ───────────────────────────────────────────
        rid = self.memory.store_response(user_input, final_answer, confidence)
        self.memory.add_turn("user", user_input)
        self.memory.add_turn("assistant", final_answer[:400])
        self.memory.store("qa", user_input[:100], final_answer[:500], float(confidence)/100)

        return AOSResponse(
            answer=final_answer,
            confidence=confidence,
            confidence_reason=conf_reason,
            task_type=route.task_type.value,
            agents_used=[r.agent for r in agent_results],
            debate_rounds=debate_rounds,
            critics_passed=critics_passed,
            sources=list(dict.fromkeys(all_sources))[:5],
            response_id=rid,
            elapsed_ms=int((time.time()-t0)*1000),
        )

    def record_feedback(self, response_id: int, useful: bool):
        self.memory.record_feedback(response_id, useful)

    def close(self):
        self.memory.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_trivial(self, text: str) -> bool:
        """Fast-path for greetings, very short queries, casual chat."""
        t = text.strip().lower()
        if len(t.split()) < 4:
            return True
        greetings = ("hi ", "hello", "hey ", "thanks", "thank you", "bye", "good morning",
                     "good night", "how are you", "what's up", "who are you")
        return any(t.startswith(g) for g in greetings)

    async def _fact_check(self, question: str, answer: str, evidence: list[dict]) -> str:
        """Layer 6 — verify key claims against search evidence."""
        ev_text = "\n".join(
            f"[{i+1}] {r.get('title','')} — {r.get('snippet','')[:200]}"
            for i, r in enumerate(evidence[:4])
        )
        return await p.think(
            prompt=(
                f"CLAIM TO VERIFY:\n{answer[:600]}\n\n"
                f"SEARCH EVIDENCE:\n{ev_text}\n\n"
                "Check if the claim is supported by the evidence. "
                "Reply: VERIFIED, PARTIALLY VERIFIED, or UNVERIFIED, and briefly explain why."
            ),
            system="You are a fact-checker. Be precise. Only use the provided evidence.",
            max_tokens=200,
            prefer="groq",
        )

    async def _final_write(
        self,
        user_input: str,
        winner: str,
        critique_summary: str,
        fact_note: str,
        confidence: int,
        sources: list[str],
    ) -> str:
        """Layer 9 — Claude rewrites the winner into the final polished answer."""
        sources_text = ""
        if sources:
            sources_text = "\nSources: " + " | ".join(sources[:3])

        system = (
            "You are the Final Writer. Your job: take the best draft answer and rewrite it "
            "into a clear, professional, complete response. Requirements:\n"
            "• Natural language — not robotic\n"
            "• Address all aspects of the question\n"
            "• Fix any issues flagged by critics\n"
            "• No contradictions, no hallucination\n"
            "• Add source citations if sources are provided\n"
            "• End with a brief note if confidence < 80%\n"
            "Return ONLY the final answer, no meta-commentary."
        )

        critics_note = f"\nCritics flagged: {critique_summary[:300]}" if critique_summary.strip() else ""
        fact_note_text = f"\nFact check: {fact_note}" if fact_note else ""
        low_conf_note = f"\n⚠️ Confidence: {confidence}% — treat with appropriate caution." if confidence < 80 else ""

        full_prompt = (
            f"USER QUESTION: {user_input}\n\n"
            f"BEST DRAFT ANSWER:\n{winner}\n"
            f"{critics_note}"
            f"{fact_note_text}"
            f"{sources_text}"
            f"{low_conf_note}\n\n"
            "Write the final polished answer:"
        )

        result = await p.call_claude(full_prompt, system, max_tokens=1500)

        # Fallback chain if Claude failed or returned empty/error
        if not result or result.startswith("[") or len(result) < 10:
            result = await p.think(
                prompt=full_prompt,
                system=system,
                max_tokens=1000,
                prefer="gemini",
            )

        # Last resort: return the winner agent's draft directly
        if not result or result.startswith("[") or len(result) < 10:
            return winner

        return result
