"""
L7 — Query Classifier + DSPy ReAct Planner

Classifies queries into one of four types using Groq Llama-3.1-8b-instant
(~100ms per classification). For complex reasoning, provides a DSPy ReAct
module that can perform multi-step tool-augmented reasoning.

Query types:
    - simple: One factual lookup, single piece of info needed
    - complex: Multiple reasoning steps, synthesis from retrieved docs
    - tool: Requires external action (web search, API call, calculation)
    - graph: Cross-document relationship query (LazyGraphRAG pattern)
"""
import logging
import dspy
from src.core.generation import fast_complete

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify this query. Reply with ONE word only: simple, complex, tool, or graph.

simple = one factual lookup, one piece of info needed
complex = requires multiple reasoning steps or synthesis from retrieved docs
tool = requires external action (web search, API call, calculation)
graph = cross-document relationship query (e.g. "what patterns across all X?", "compare Y and Z across documents")

Query: {query}
Category:"""


async def classify_query(query: str) -> str:
    """Classify a query into simple/complex/tool/graph.

    Uses fast Groq 8b model (~100ms). Defaults to 'simple' on any failure
    to ensure the system never crashes due to classification errors.

    Args:
        query: The user's question to classify.

    Returns:
        One of: "simple", "complex", "tool", "graph"
    """
    try:
        result = await fast_complete(CLASSIFY_PROMPT.format(query=query), max_tokens=5)
        label = result.strip().lower()
        return label if label in ("simple", "complex", "tool", "graph") else "simple"
    except Exception as e:
        logger.warning(f"[non-critical] classify_query failed, defaulting to 'simple': {type(e).__name__}: {e}")
        return "simple"


class SynapseReAct(dspy.Module):
    """Multi-step reasoning agent using DSPy ReAct.

    Maximum 5 iterations before forced synthesis. Available tools:
    retrieve_knowledge, web_search, call_api, calculate.
    """

    def __init__(self, tools: list, max_iters: int = 5):
        super().__init__()
        self.react = dspy.ReAct(
            signature="session_context, long_term_memory, question -> answer",
            tools=tools,
            max_iters=max_iters,
        )

    def forward(self, question: str, session_context: str, long_term_memory: str):
        """Execute the ReAct reasoning loop."""
        return self.react(
            question=question,
            session_context=session_context,
            long_term_memory=long_term_memory,
        )
