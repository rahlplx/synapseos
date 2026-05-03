"""
L7 — Query Classifier + DSPy ReAct Planner
Classifier uses Groq Llama-3.1-8b-instant (fast, cheap). ReAct uses DSPy for complex reasoning.
"""
import dspy
from src.core.generation import fast_complete

CLASSIFY_PROMPT = """Classify this query. Reply with ONE word only: simple, complex, or tool.

simple = one factual lookup, one piece of info needed
complex = requires multiple reasoning steps or synthesis
tool = requires external action (web search, API call, calculation)

Query: {query}
Category:"""


async def classify_query(query: str) -> str:
    """Classify a query into simple/complex/tool.
    Uses fast Groq 8b model (~100ms). Defaults to 'simple' on any failure.
    """
    try:
        result = await fast_complete(CLASSIFY_PROMPT.format(query=query), max_tokens=5)
        label = result.strip().lower()
        return label if label in ("simple", "complex", "tool") else "simple"
    except Exception:
        return "simple"


class SynapseReAct(dspy.Module):
    """Multi-step reasoning agent. Max 5 iterations before forced synthesis.
    Tools available: retrieve_knowledge, web_search, call_api, calculate.
    """
    def __init__(self, tools: list, max_iters: int = 5):
        super().__init__()
        self.react = dspy.ReAct(
            signature="session_context, long_term_memory, question -> answer",
            tools=tools,
            max_iters=max_iters,
        )

    def forward(self, question: str, session_context: str, long_term_memory: str):
        return self.react(
            question=question,
            session_context=session_context,
            long_term_memory=long_term_memory,
        )
