from agno.agent import Agent
from agno.models.openai import OpenAIChat

def writer_agent(url_kb, language: str = "fr") -> Agent:
    return Agent(
        name="Writer",
        role=(
            "Rédige une newsletter structurée (Highlights, À la une, Papiers, Outils, Réseaux)."
        ),
        model=OpenAIChat(id="gpt-4o"),
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            f"Langue: {language}.",
            "Chaque affirmation importante est sourcée (liens).",
            "Tonalité: concise, professionnelle, accessible.",
        ],
    )