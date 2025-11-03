from agno.agent import Agent
from agno.models.openai import OpenAIChat
from src.knowledge.vector_db import kb_search_urls as _kb_search_urls

def rag_agent(url_kb, language: str = "fr") -> Agent:
    return Agent(
        name="RAG-QA",
        role=(
            "Répondre aux questions uniquement avec la base de connaissances. Toujours citer les URL."
        ),
        model=OpenAIChat(id="gpt-4o"),
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=False,
        instructions=[
            f"Langue: {language}.",
            "Si le contexte contient du HTML, ignorer les balises et ne conserver que le texte.",
            "Retourner un JSON strict: 'answer' (4–10 phrases Markdown) et 'citations' (url,title).",
            "Ne pas inventer d'URL.",
        ],
    )


def kb_search_urls(query: str, url_kb, k: int = 5):
    return _kb_search_urls(query, url_kb, k)

