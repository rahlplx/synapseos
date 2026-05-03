"""
L7 — Query Classifier + DSPy ReAct Planner
Classifier uses FREE z.ai flash. ReAct uses GLM-5.1 for complex reasoning.
"""
import dspy
from src.core.generation import fast_complete

CLASSIFY_PROMPT = """Classify this query. Reply with ONE word only: simple, complex, or tool.

simple = one factual lookup
complex = needs multiple reasoning steps or synthesis  
tool = needs external action (web search, API call, calculation)

Query: {query}
Category:"""


async def classify_query(query: str) -> str:
    result = await fast_complete(CLASSIFY_PROMPT.format(query=query), max_tokens=5)
    label = result.strip().lower()
    return label if label in ("simple", "complex", "tool") else "simple"


class SynapseReAct(dspy.Module):
    """Multi-step reasoning agent. Max 5 iterations before forced synthesis."""
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
