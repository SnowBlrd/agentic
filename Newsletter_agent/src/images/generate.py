import base64
from pathlib import Path
from openai import OpenAI
from agno.agent import Agent
from agno.models.openai import OpenAIChat


def craft_image_prompt_from_newsletter(news_md: str) -> str:
    art = Agent(
        name="ArtDirector",
        role=(
            "Conçoit un prompt d'image original inspiré du contenu de la newsletter : "
            "métaphores, éléments visuels, ambiance. Pas de texte dans l'image."
        ),
        model=OpenAIChat(id="gpt-4o-mini"),
        markdown=False,
        instructions=[
            "Le prompt doit tenir en 1–2 phrases (max 60 mots).",
            "Décrire le sujet, le cadrage/angle, l'ambiance/couleurs, le style (illustration/3D/flat).",
            "Aucune info sensible ni logos de marques. Pas de texte dans l'image.",
        ],
    )
    resp = art.run(
        """
À partir de la newsletter ci-dessous, écris un UNIQUE prompt d'image qui symbolise l'actualité IA de la semaine.
Contraintes :
- Pas de texte dans l'image.
- Style cohérent avec une newsletter tech professionnelle.
- Mentionner cadrage (ex: wide banner), ambiance et 1–2 éléments clés.
Retourne UNIQUEMENT le prompt, sans commentaire.
---
""" + news_md
    )
    return (resp.content or "")[:500].strip()


def generate_header_image(prompt: str, out_dir: Path, date: str, size: str = "1024x1024") -> Path:
    client = OpenAI()
    res = client.images.generate(model="gpt-image-1", prompt=prompt, size=size)
    b64 = res.data[0].b64_json
    out_path = out_dir.joinpath(f"banner_{date}.png")
    out_path.write_bytes(base64.b64decode(b64))
    out_dir.joinpath(f"banner_prompt_{date}.txt").write_text(prompt, encoding="utf-8")
    return out_path