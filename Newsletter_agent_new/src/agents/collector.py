from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.newspaper4k import Newspaper4kTools

def collector_agent(url_kb) -> Agent:
    return Agent(
        name="Collector",
        role=(
            "Récupère des sources (arXiv, RSS, web explicite). "
            "Pour chaque lien, extrait titre/auteurs/date et ajoute au KB."
        ),
        model=OpenAIChat(id="gpt-4o-mini"),
        tools=[DuckDuckGoTools(), Newspaper4kTools()],
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            "Toujours retourner des JSON linéarisés si demandé.",
            "Citer les URL trouvées.",
        ],
    )