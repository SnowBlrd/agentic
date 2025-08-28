# context_agent.py
from __future__ import annotations

"""
Agent Agno 'ContextBuilder' pour résumer des documents (PDF, DOCX, PPTX, code/texte, notebooks)
dans le cadre de réunions data (weekly/projets). L'agent expose un tool `load_document` qui
extrait le texte, puis renvoie un JSON structuré prêt à être stocké et réutilisé.

Dépendances (requirements.txt) :
- agno
- streamlit (utilisé ailleurs dans l'app)
- python-docx
- python-pptx
- pypdf
- chardet
- openai
"""

import os
import re
import io
import json
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Agno
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool

# ----------------------------------------------------------------------
# Lecture de fichiers
# ----------------------------------------------------------------------

MAX_CHARS_DEFAULT = 20_000


def _read_text_docx(path: str) -> Dict[str, Any]:
    from docx import Document
    doc = Document(path)
    paras: List[str] = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    # tables
    for t in doc.tables:
        for row in t.rows:
            paras.append(" | ".join(cell.text.strip() for cell in row.cells))
    text = "\n".join(paras)
    return {
        "doc_type": "docx",
        "text": text,
        "pages_or_slides": None,
    }


def _read_text_pptx(path: str) -> Dict[str, Any]:
    from pptx import Presentation
    prs = Presentation(path)
    chunks: List[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        slide_text: List[str] = []
        for shp in slide.shapes:
            if hasattr(shp, "text") and shp.text:
                slide_text.append(shp.text)
        # notes du présentateur
        if slide.has_notes_slide and slide.notes_slide and slide.notes_slide.notes_text_frame:
            slide_text.append(slide.notes_slide.notes_text_frame.text)
        if slide_text:
            chunks.append(f"[Slide {i}] " + " \n".join(t.strip() for t in slide_text if t and t.strip()))
    text = "\n\n".join(chunks)
    return {
        "doc_type": "pptx",
        "text": text,
        "pages_or_slides": len(prs.slides),
    }


def _read_text_pdf(path: str) -> Dict[str, Any]:
    # Extraction texte (pas d'OCR pour les PDF scannés)
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    chunks: List[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            chunks.append(f"[Page {i}] {txt.strip()}")
    text = "\n\n".join(chunks).strip()
    return {
        "doc_type": "pdf",
        "text": text,
        "pages_or_slides": len(reader.pages),
    }


def _read_text_code_or_text(path: str) -> Dict[str, Any]:
    import chardet
    p = pathlib.Path(path)
    raw = p.read_bytes()
    enc = chardet.detect(raw).get("encoding") or "utf-8"
    text = raw.decode(enc, errors="ignore")
    # Traitement basique des notebooks : garder markdown + signatures de cellules code
    if p.suffix.lower() == ".ipynb":
        try:
            nb = json.loads(text)
            cells = nb.get("cells", [])
            parts: List[str] = []
            for c in cells:
                if c.get("cell_type") == "markdown":
                    parts.append("".join(c.get("source", [])))
                elif c.get("cell_type") == "code":
                    parts.append("```code\n" + "".join(c.get("source", [])) + "\n```")
            text = "\n\n".join(parts)
        except Exception:
            # si invalide, on laisse tel quel
            pass
    return {
        "doc_type": "code_or_text",
        "text": text,
        "pages_or_slides": None,
    }


def _read_text_auto(path: str, max_chars: int = MAX_CHARS_DEFAULT) -> Dict[str, Any]:
    """
    Détecte le type de fichier par extension et extrait le texte.
    """
    p = pathlib.Path(path)
    ext = p.suffix.lower()

    if ext == ".docx":
        info = _read_text_docx(path)
    elif ext == ".pptx":
        info = _read_text_pptx(path)
    elif ext == ".pdf":
        info = _read_text_pdf(path)
    else:
        info = _read_text_code_or_text(path)

    text = info.get("text", "")[:max_chars]
    info["text"] = text
    info["chars"] = len(text)
    info["words"] = len(re.findall(r"\w+", text, flags=re.UNICODE))
    info["filename"] = p.name
    return info


# ----------------------------------------------------------------------
# Tool Agno
# ----------------------------------------------------------------------

@tool(
    name="load_document",
    description="Charger un fichier (pdf, docx, pptx, code, txt, ipynb) et renvoyer du texte brut tronqué."
)
def load_document(path: str, max_chars: int = MAX_CHARS_DEFAULT) -> Dict[str, Any]:
    """
    Args:
        path: chemin absolu/relatif vers le fichier.
        max_chars: limite de caractères à renvoyer (contrôle du coût prompt).
    Returns:
        dict { doc_type, text, pages_or_slides, chars, words, filename }
    """
    if not path or not pathlib.Path(path).exists():
        raise RuntimeError(f"Fichier introuvable: {path}")
    return _read_text_auto(path, max_chars=max_chars)


# ----------------------------------------------------------------------
# Instructions de l'agent
# ----------------------------------------------------------------------

SYSTEM_PROMPT = r"""
Tu es *ContextBuilder*, un agent spécialisé pour des réunions de data science (weekly & projets).

Règles:
1) Utilise OBLIGATOIREMENT l’outil `load_document(path=...)` pour lire le fichier.
2) Analyse et résume en mettant en avant:
   - Objectif du document, scope et livrables.
   - Points clés / décisions / TODOs.
   - Éléments techniques (datasets, features, modèles, métriques, dépendances, modules de code, APIs).
   - Risques, blocages, inconnues.
3) Réponds en JSON STRICT, sans texte autour, suivant ce schéma:

{
  "title": "string",
  "doc_type": "pptx|docx|pdf|code_or_text",
  "size": {"chars": int, "words": int, "pages_or_slides": int|null},
  "summary": "string",
  "key_points": ["..."],
  "actions": ["..."],
  "tech": {
    "datasets_or_tables": ["..."],
    "models_or_algorithms": ["..."],
    "metrics": ["..."],
    "code_artifacts": ["fichiers, modules, entrypoints"]
  },
  "glossary": [{"term": "string", "definition": "string"}],
  "file": "filename.ext"
}

Notes:
- Si le contenu est très long, produis une synthèse hiérarchique utile au compte rendu de réunion.
- Si un PDF ne contient pas de texte (scan), indique-le brièvement dans 'summary' et laisse les listes vides.
"""


# ----------------------------------------------------------------------
# Agent + API Python
# ----------------------------------------------------------------------

def _extract_first_json(text: str) -> Dict[str, Any]:
    """
    Tente de parser un objet JSON depuis une sortie potentiellement bruitée.
    - 1) essai direct json.loads
    - 2) recherche du premier bloc {...} équilibré
    """
    text = (text or "").strip()
    # Essai direct
    try:
        return json.loads(text)
    except Exception:
        pass

    # Recherche d’un bloc JSON { ... } équilibré
    start = text.find("{")
    if start == -1:
        raise RuntimeError(f"Réponse inattendue (pas d'accolade ouvrante): {text[:400]}")

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    break  # continue pour chercher autre chose

    # fallback regex (moins sûr, mais utile parfois)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    raise RuntimeError(f"Réponse inattendue (JSON introuvable): {text[:600]}")


@dataclass
class ContextAgent:
    """
    Façade simple autour d'un Agent Agno configuré pour produire un JSON structuré.
    """
    model_id: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def build(self) -> Agent:

        return Agent(
            model=OpenAIChat(id=self.model_id),
            description="Agent pour résumer des documents et du code dans un contexte de réunions data.",
            instructions=SYSTEM_PROMPT,
            tools=[load_document],
            markdown=False
        )

    def summarize_file(self, path: str, max_chars: int = MAX_CHARS_DEFAULT) -> Dict[str, Any]:
        agent = self.build()
        prompt = (
            f"Chemin du fichier: {path}\n"
            f"1) Appelle load_document(path='{path}', max_chars={max_chars})\n"
            f"2) Produit le JSON strict demandé."
        )
        rr = agent.run(prompt)                 # RunResponse
        payload = getattr(rr, "content", rr)   # contenu renvoyé par l'agent

        if isinstance(payload, dict):
            data = payload                     # parfois dict si modèle/agent renvoie déjà du JSON
        else:
            data = _extract_first_json(str(payload))  # sinon: extraire l'objet JSON depuis du texte

        # Normalisation minimale (comme avant)
        data["file"] = data.get("file") or pathlib.Path(path).name
        data.setdefault("key_points", [])
        data.setdefault("actions", [])
        data.setdefault("tech", {"datasets_or_tables": [], "models_or_algorithms": [], "metrics": [], "code_artifacts": []})
        data.setdefault("glossary", [])
        data["size"] = data.get("size", {}) or {}
        return data

    def summarize_many(self, paths: List[str], max_chars: int = MAX_CHARS_DEFAULT) -> List[Dict[str, Any]]:
        """
        Résume plusieurs fichiers, renvoyant une liste de JSON.
        """
        results: List[Dict[str, Any]] = []
        for p in paths:
            try:
                results.append(self.summarize_file(p, max_chars=max_chars))
            except Exception as e:
                results.append({
                    "title": None,
                    "doc_type": None,
                    "size": {"chars": 0, "words": 0, "pages_or_slides": None},
                    "summary": "",
                    "key_points": [],
                    "actions": [],
                    "tech": {"datasets_or_tables": [], "models_or_algorithms": [], "metrics": [], "code_artifacts": []},
                    "glossary": [],
                    "file": pathlib.Path(p).name,
                    "error": str(e),
                })
        return results


# ----------------------------------------------------------------------
# Exécution CLI (facultatif) : `python context_agent.py path1 path2 ...`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import pprint

    if len(sys.argv) < 2:
        print("Usage: python context_agent.py <fichier1> [<fichier2> ...]")
        sys.exit(1)

    agent = ContextAgent()
    for fp in sys.argv[1:]:
        try:
            res = agent.summarize_file(fp)
            pprint.pp(res, width=100)
        except Exception as e:
            print(f"[ERREUR] {fp}: {e}")
