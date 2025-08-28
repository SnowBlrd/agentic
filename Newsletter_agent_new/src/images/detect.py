import os
import io
import uuid
import base64
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from PIL import Image
from urllib.parse import urljoin
from openai import OpenAI

DEFAULT_IMG_KEYWORDS = [
    "ia", "intelligence artificielle", "artificial intelligence", "ai",
    "machine learning", "apprentissage", "neuronal", "neurone", "neural",
    "llm", "agents", "genai", "transformer",
]


def _download_and_probe_image(img_url: str, dest_dir: Path):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (image-detector)"}
        r = requests.get(img_url, timeout=12, stream=True, headers=headers)
        r.raise_for_status()
        content = r.content
        im = Image.open(io.BytesIO(content)).convert("RGB")
        width, height = im.size
        fname = f"det_{uuid.uuid4().hex[:8]}.png"
        path = dest_dir.joinpath(fname)
        im.save(path, format="PNG")
        return str(path), width, height
    except Exception:
        return None


def _score_candidate(width: int, height: int, alt: str, keywords: List[str]) -> float:
    area = width * height
    ar = width / max(1, height)
    score = min(area / 1_000_000.0, 4.0)
    if ar >= 1.5:
        score += 0.6
    alt_l = (alt or "").lower()
    if any(k.lower() in alt_l for k in keywords):
        score += 1.0
    if width >= 1400:
        score += 0.4
    if height >= 700:
        score += 0.3
    return round(score, 3)


def _is_image_safe(local_path: str) -> bool:
    if os.getenv("ENABLE_VISION_SAFETY", "0") != "1":
        return True
    try:
        client = OpenAI()
        with open(local_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        messages = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Dis 'OK' si l'image est adaptée à une newsletter tech (pas de nudité explicite, violence graphique, haine). Sinon 'REFUSER'."},
                {"type": "input_image", "image_url": data_url},
            ],
        }]
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=10)
        txt = (resp.choices[0].message.content or "").lower()
        return ("ok" in txt) and ("refuser" not in txt)
    except Exception:
        return True


def _fetch_page_images(source_url: str, dest_dir: Path, keywords: List[str], min_w: int, min_h: int, max_imgs: int = 3):
    headers = {"User-Agent": "Mozilla/5.0 (image-detector)"}
    out = []
    try:
        r = requests.get(source_url, timeout=12, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        imgs = soup.find_all("img")
        count = 0
        for tag in imgs:
            src = tag.get("src") or tag.get("data-src") or tag.get("data-original")
            if not src:
                continue
            abs_url = urljoin(source_url, src)
            alt = tag.get("alt", "")
            probed = _download_and_probe_image(abs_url, dest_dir)
            if not probed:
                continue
            local_path, w, h = probed
            if w < min_w or h < min_h:
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                continue
            if not _is_image_safe(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                continue
            score = _score_candidate(w, h, alt, keywords)
            out.append({
                "local_path": local_path,
                "source_page": source_url,
                "width": w,
                "height": h,
                "alt": alt,
                "score": score,
            })
            count += 1
            if count >= max_imgs:
                break
    except Exception:
        pass
    return out


def detect_best_header_image(url_kb, cfg: dict, out_dir: Path, date: str) -> Optional[Path]:
    max_pages = int(os.getenv("IMAGE_DETECT_MAX_PAGES", "20"))
    min_w = int(os.getenv("IMAGE_MIN_WIDTH", "900"))
    min_h = int(os.getenv("IMAGE_MIN_HEIGHT", "500"))
    keywords = cfg.get("keywords", DEFAULT_IMG_KEYWORDS)

    dest = out_dir.joinpath("assets", date)
    dest.mkdir(parents=True, exist_ok=True)

    urls = url_kb.urls[:max_pages]
    all_cands = []
    for u in urls:
        all_cands.extend(_fetch_page_images(u, dest, keywords, min_w, min_h, max_imgs=3))

    if not all_cands:
        return None
    best = max(all_cands, key=lambda c: c["score"])
    return Path(best["local_path"])