"""
Layer 4 — Specialist Agents
Each agent is an expert with a focused role and preferred AI provider.
All agents run asynchronously so they can execute in parallel.
"""
import asyncio
from dataclasses import dataclass, field
from . import providers as p


@dataclass
class AgentResult:
    agent:      str
    answer:     str
    provider:   str
    confidence: int = 0       # agent's self-assessed confidence 0-100
    sources:    list[str] = field(default_factory=list)
    reasoning:  str = ""


# ── Base Agent ────────────────────────────────────────────────────────────────

class BaseAgent:
    name     = "base"
    role     = "General assistant"
    provider = "claude"

    async def run(self, task: str, context: str = "", search_results: list = None) -> AgentResult:
        answer = await p.think(
            prompt=self._build_prompt(task, context, search_results),
            system=self._system(),
            max_tokens=self._max_tokens(),
            prefer=self.provider,
        )
        return AgentResult(agent=self.name, answer=answer, provider=self.provider)

    def _system(self) -> str:
        return f"You are an expert {self.role}. Be precise, evidence-based, and thorough."

    def _build_prompt(self, task: str, context: str, search_results: list) -> str:
        parts = [f"TASK: {task}"]
        if context:
            parts.append(f"\nCONTEXT:\n{context[:800]}")
        if search_results:
            snips = "\n".join(
                f"[{i+1}] {r.get('title','')} — {r.get('snippet','')[:200]}"
                for i, r in enumerate(search_results[:5])
            )
            parts.append(f"\nSEARCH EVIDENCE:\n{snips}")
        parts.append("\nProvide your expert answer:")
        return "\n".join(parts)

    def _max_tokens(self) -> int:
        return 800

    async def revise(self, task: str, my_answer: str, others_answers: list[str]) -> str:
        """Revise answer after seeing peers' work (debate round)."""
        others_text = "\n\n".join(
            f"--- PEER {i+1} ---\n{ans[:400]}" for i, ans in enumerate(others_answers)
        )
        return await p.think(
            prompt=(
                f"TASK: {task}\n\n"
                f"YOUR PREVIOUS ANSWER:\n{my_answer[:600]}\n\n"
                f"PEER ANSWERS TO CONSIDER:\n{others_text}\n\n"
                "Revise your answer incorporating the best insights from peers. "
                "If your answer was already better, keep it with minor improvements. "
                "Reply with ONLY the revised answer:"
            ),
            system=self._system(),
            max_tokens=self._max_tokens(),
            prefer=self.provider,
        )


# ── Specialist Agents ─────────────────────────────────────────────────────────

class PlannerAgent(BaseAgent):
    name     = "planner"
    role     = "strategic planning expert who breaks complex problems into clear steps"
    provider = "claude"

    def _system(self) -> str:
        return (
            "You are an elite strategic planner. Break the given task into a clear, "
            "numbered action plan. For each step: what, why, expected output. "
            "Be specific and actionable. Think like a McKinsey consultant."
        )

    def _max_tokens(self) -> int:
        return 600


class ResearchAgent(BaseAgent):
    name     = "researcher"
    role     = "deep research specialist"
    provider = "gemini"

    def _system(self) -> str:
        return (
            "You are a world-class researcher. Provide comprehensive, well-structured "
            "research on the topic. Include: background, key facts, expert consensus, "
            "contrasting views, and recent developments. Cite evidence. "
            "If search results are provided, use them. Flag anything uncertain."
        )

    def _max_tokens(self) -> int:
        return 1200


class ReasoningAgent(BaseAgent):
    name     = "reasoner"
    role     = "logical reasoning and analysis expert"
    provider = "gemini"

    def _system(self) -> str:
        return (
            "You are an expert in logic and reasoning. Analyze the problem step by step. "
            "Identify assumptions, evaluate evidence, spot logical fallacies, "
            "and arrive at a well-justified conclusion. Use chain-of-thought reasoning. "
            "Explicitly state your confidence in each step."
        )

    def _max_tokens(self) -> int:
        return 1000


class CodingAgent(BaseAgent):
    name     = "coder"
    role     = "senior software engineer"
    provider = "deepseek"

    def _system(self) -> str:
        return (
            "You are a senior software engineer. Write clean, efficient, well-commented code. "
            "Include: the solution, explanation of approach, time/space complexity, "
            "edge cases handled, and usage example. Prefer readability over cleverness."
        )

    def _max_tokens(self) -> int:
        return 2000


class MathAgent(BaseAgent):
    name     = "math"
    role     = "mathematics and quantitative reasoning expert"
    provider = "deepseek"

    def _system(self) -> str:
        return (
            "You are a mathematics expert. Solve the problem step by step, showing all work. "
            "State assumptions clearly, verify the answer by substitution or alternative method. "
            "Give the final answer clearly labeled."
        )

    def _max_tokens(self) -> int:
        return 800


class SearchAgent(BaseAgent):
    name     = "searcher"
    role     = "information retrieval specialist"
    provider = "groq"

    async def run(self, task: str, context: str = "", search_results: list = None) -> AgentResult:
        # Always does a fresh search
        results = await p.search(task, num=6)
        if not results:
            results = search_results or []

        sources = [r.get("url","") for r in results if r.get("url")]
        evidence = "\n".join(
            f"[{i+1}] {r.get('title','')} — {r.get('snippet','')[:300]}"
            for i, r in enumerate(results[:5])
        )
        answer = await p.think(
            prompt=(
                f"QUESTION: {task}\n\n"
                f"SEARCH RESULTS:\n{evidence}\n\n"
                "Synthesize the search results into a direct, factual answer. "
                "Reference the numbered sources. Flag if evidence is insufficient:"
            ),
            system="You are a research librarian. Extract factual answers from search results. Be precise.",
            max_tokens=600,
            prefer=self.provider,
        )
        return AgentResult(agent=self.name, answer=answer, provider=self.provider, sources=sources)


class VisionAgent(BaseAgent):
    name     = "vision"
    role     = "visual analysis expert"
    provider = "gemini"

    def _system(self) -> str:
        return (
            "You are an expert at analyzing visual content. Describe what you see in detail, "
            "extract text (OCR), identify objects, people, patterns, and answer questions about "
            "the visual content. Be precise and thorough."
        )


class WritingAgent(BaseAgent):
    name     = "writer"
    role     = "professional writer and editor"
    provider = "claude"

    def _system(self) -> str:
        return (
            "You are a professional writer. Produce clear, engaging, well-structured text. "
            "Match the appropriate tone (formal/casual/technical). Eliminate jargon. "
            "Every sentence should earn its place. Edit for clarity and impact."
        )

    def _max_tokens(self) -> int:
        return 1200


class TranslationAgent(BaseAgent):
    name     = "translator"
    role     = "professional translator"
    provider = "groq"

    def _system(self) -> str:
        return (
            "You are a professional translator. Translate accurately, preserving tone, "
            "nuance, and cultural context. If the target language is unclear, ask. "
            "Provide the translation only, unless the user asks for explanation."
        )

    def _max_tokens(self) -> int:
        return 1000


class MemoryAgent(BaseAgent):
    name     = "memory"
    role     = "memory retrieval and context specialist"
    provider = "groq"

    def _system(self) -> str:
        return (
            "You synthesize retrieved memories and context to provide relevant background. "
            "Identify what from the user's history is relevant to the current task."
        )


# ── Agent Registry ────────────────────────────────────────────────────────────

AGENT_MAP: dict[str, BaseAgent] = {
    "planner":    PlannerAgent(),
    "researcher": ResearchAgent(),
    "reasoner":   ReasoningAgent(),
    "coder":      CodingAgent(),
    "math":       MathAgent(),
    "searcher":   SearchAgent(),
    "vision":     VisionAgent(),
    "writer":     WritingAgent(),
    "translator": TranslationAgent(),
    "memory":     MemoryAgent(),
}


async def run_agents_parallel(
    agent_names: list[str],
    task: str,
    context: str = "",
    search_results: list = None,
) -> list[AgentResult]:
    """Run all requested agents in parallel, return their results."""
    agents = [AGENT_MAP[n] for n in agent_names if n in AGENT_MAP]
    if not agents:
        agents = [AGENT_MAP["writer"]]
    tasks = [a.run(task, context, search_results) for a in agents]
    return await asyncio.gather(*tasks, return_exceptions=False)
