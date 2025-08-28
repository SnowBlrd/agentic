from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.reasoning import ReasoningTools

def curator_agent(url_kb) -> Agent:
    return Agent(
        name="Curator",
        role=(
            "Clusterise les items par sujet et évalue leur qualité: nouveauté, crédibilité, clarté, impact."
        ),
        model=OpenAIChat(id="gpt-4o"),
        tools=[ReasoningTools(add_instructions=True)],
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            "Produire des topics concis (2–5 mots).",
            "Expliquer la priorisation en 1–2 phrases par cluster.",
        ],
    )
