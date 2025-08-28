# context_orchestrator_agent.py
from __future__ import annotations
import os
from typing import List, Dict, Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool

from context_agent import ContextAgent, MAX_CHARS_DEFAULT
from local_store import LocalStore

# Config simples via env
MODEL_ID = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
STORE_DIR = os.getenv("CONTEXT_STORE_DIR", ".context_store")
_store = LocalStore(STORE_DIR)
_summarizer = ContextAgent(model_id=MODEL_ID)

@tool(name="ingest_file", description="Résumé + stockage local d’un document (pdf/docx/pptx/code).")
def ingest_file(path: str, max_chars: int = MAX_CHARS_DEFAULT) -> Dict[str, Any]:
    data = _summarizer.summarize_file(path, max_chars=max_chars)
    saved = _store.upsert(data)
    return {
        "ok": True,
        "id": saved.get("_path"),
        "file": saved.get("file"),
        "title": saved.get("title"),
        "size": saved.get("size"),
    }

@tool(name="list_context", description="Lister les résumés présents en local.")
def list_context() -> List[Dict[str, Any]]:
    items = _store.list()
    return [
        {"id": it.get("_path"), "file": it.get("file"), "title": it.get("title"), "size": it.get("size")}
        for it in items
    ]

@tool(name="search_context", description="Recherche mot-clé dans summary/key_points; renvoie les éléments correspondants.")
def search_context(query: str) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    out = []
    for it in _store.list():
        blob = (it.get("summary", "") + " " + " ".join(it.get("key_points", []))).lower()
        if q and q in blob:
            out.append({"id": it.get("_path"), "file": it.get("file"), "title": it.get("title")})
    return out

@tool(name="delete_context_item", description="Supprime un résumé via son id (chemin du fichier JSON).")
def delete_context_item(item_id: str) -> Dict[str, Any]:
    ok = _store.delete(item_id)
    return {"ok": ok, "id": item_id}

SYSTEM_PROMPT = """
Tu es **AgentContexte**, assistant pour réunions data.
- Utilise de préférence les tools pour INGESTER (ingest_file), LISTER (list_context),
  CHERCHER (search_context) et SUPPRIMER (delete_context_item).
- Réponds de façon concise et opérationnelle.
- Si un utilisateur donne un chemin de fichier, ingère-le (ingest_file).
- Si le PDF semble scanné (résumé vide), signale que l’OCR peut être nécessaire.
"""

def build_agent() -> Agent:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY manquant (secrets.toml ou env).")
    return Agent(
        model=OpenAIChat(id=MODEL_ID, api_key=api_key),
        instructions=SYSTEM_PROMPT,
        tools=[ingest_file, list_context, search_context, delete_context_item],
        markdown=True,
    )
