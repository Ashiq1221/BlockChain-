"""
Task Router — classifies user input and returns the specialist agent assignment.
"""
import re
from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    CODING       = "coding"
    RESEARCH     = "research"
    MATH         = "math"
    WRITING      = "writing"
    VISION       = "vision"
    TRANSLATION  = "translation"
    SEARCH       = "search"
    MEMORY       = "memory"
    AUTOMATION   = "automation"
    CONVERSATION = "conversation"
    ANALYSIS     = "analysis"
    GENERAL      = "general"


@dataclass
class RouteResult:
    task_type:   TaskType
    agents:      list[str]        # agent names to activate
    preferred_provider: str       # primary AI provider
    needs_search: bool = False
    needs_memory: bool = True
    needs_debate: bool = True
    complexity:  str = "medium"   # simple / medium / complex
    subtasks:    list[str] = field(default_factory=list)


# ── Keyword-based fast classification ─────────────────────────────────────────

_CODING_KW   = r'\b(code|program|script|function|class|bug|debug|implement|api|sql|python|javascript|rust|algorithm|compile|error|exception|stack|array|loop|class|interface|refactor|optimize|unittest|async|await)\b'
_MATH_KW     = r'\b(calculate|compute|solve|equation|integral|derivative|probability|statistics|formula|algebra|geometry|matrix|vector|proof|theorem|sum|average|percentage|sqrt|sin|cos|log)\b'
_RESEARCH_KW = r'\b(research|study|compare|analyze|explain|overview|history|background|literature|survey|what is|who is|when did|why does|how does|tell me about|describe)\b'
_WRITING_KW  = r'\b(write|draft|essay|article|blog|email|letter|report|summary|rewrite|paraphrase|tone|style|grammar|proofread|translate|poem|story|caption|post)\b'
_TRANSLATION_KW = r'\b(translate|translation|language|spanish|french|arabic|chinese|hindi|german|japanese|korean|portuguese|italian|turkish|russian)\b'
_SEARCH_KW   = r'\b(latest|recent|current|today|news|2025|2026|price|live|trending|now|find|search for|look up)\b'
_VISION_KW   = r'\b(image|photo|picture|screenshot|diagram|chart|visual|see|look at|analyze this image|what.s in)\b'
_MATH_FAST   = r'[\d\+\-\*\/\=\^\(\)\%]{4,}'   # expression like 2+2 or (3*4)/2


def classify(user_input: str) -> RouteResult:
    txt = user_input.lower()

    # Vision — if image present, always vision
    if re.search(_VISION_KW, txt):
        return RouteResult(
            task_type=TaskType.VISION,
            agents=["vision", "writer"],
            preferred_provider="gemini",
            needs_search=False,
            complexity="medium",
        )

    # Translation
    if re.search(_TRANSLATION_KW, txt):
        return RouteResult(
            task_type=TaskType.TRANSLATION,
            agents=["translator", "writer"],
            preferred_provider="groq",
            needs_search=False,
            needs_debate=False,
            complexity="simple",
        )

    # Math / calculation
    if re.search(_MATH_KW, txt) or re.search(_MATH_FAST, txt):
        return RouteResult(
            task_type=TaskType.MATH,
            agents=["math", "reasoner", "critic"],
            preferred_provider="deepseek",
            needs_search=False,
            complexity="medium",
        )

    # Coding
    if re.search(_CODING_KW, txt):
        return RouteResult(
            task_type=TaskType.CODING,
            agents=["coder", "critic", "security"],
            preferred_provider="deepseek",
            needs_search=False,
            complexity="complex",
        )

    # Search / latest news
    if re.search(_SEARCH_KW, txt):
        return RouteResult(
            task_type=TaskType.SEARCH,
            agents=["searcher", "researcher", "writer"],
            preferred_provider="claude",
            needs_search=True,
            complexity="medium",
        )

    # Writing
    if re.search(_WRITING_KW, txt):
        return RouteResult(
            task_type=TaskType.WRITING,
            agents=["writer", "critic"],
            preferred_provider="claude",
            needs_search=False,
            complexity="medium",
        )

    # Research / explanation
    if re.search(_RESEARCH_KW, txt):
        return RouteResult(
            task_type=TaskType.RESEARCH,
            agents=["researcher", "reasoner", "searcher", "writer"],
            preferred_provider="gemini",
            needs_search=True,
            complexity="complex",
        )

    # Short conversation
    if len(txt.split()) < 10:
        return RouteResult(
            task_type=TaskType.CONVERSATION,
            agents=["writer"],
            preferred_provider="claude",
            needs_search=False,
            needs_debate=False,
            complexity="simple",
        )

    # Default — general analysis
    return RouteResult(
        task_type=TaskType.GENERAL,
        agents=["planner", "researcher", "reasoner", "writer"],
        preferred_provider="claude",
        needs_search=True,
        complexity="complex",
    )
