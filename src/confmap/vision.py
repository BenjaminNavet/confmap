"""Analyse d'une photo (slide, tableau, poster) : seul le texte extrait est conservé."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

from confmap.llm import ImageInput, LlmClient, LlmResult

MAX_SIDE = 1568

SYSTEM = """Tu aides un chercheur à suivre une conférence. Il photographie l'écran (slides) ou un support.
Extrais en français le contenu informatif de la photo, pour ses notes :
- titre de la slide, points clés, données chiffrées, formules, noms de méthodes, auteurs et références citées ;
- pour un schéma ou un graphique : ce qu'il montre (axes, tendances, comparaisons) en 1 à 3 phrases ;
- garde entre parenthèses le terme d'origine des termes techniques traduits ;
- ignore le décor, la salle, l'orateur, les logos ; ne décris pas la photo elle-même.
"title" = titre de la slide (traduit) ; "content" = le reste, sans répéter le titre, sans titres Markdown (#), en puces simples. Sois concis (au plus ~120 mots). Si la photo ne contient rien d'informatif, renvoie un texte vide."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["title", "content"],
    "additionalProperties": False,
}


def prepare_image(raw: bytes) -> bytes:
    """Corrige l'orientation, réduit à 1568 px de côté max, encode en JPEG."""
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


async def analyze_photo(
    client: LlmClient, model: str, context: str, recent_speech: str, raw_image: bytes
) -> tuple[str, LlmResult]:
    """Retourne le texte extrait de la photo (vide si rien d'utile)."""
    prompt = (
        f"CONTEXTE : {context or '(aucun)'}\n"
        f'CE QUE DIT L\'ORATEUR EN CE MOMENT : "{recent_speech[-1500:]}"\n\n'
        "Extrais le contenu de cette photo."
    )
    image = ImageInput(prepare_image(raw_image), "image/jpeg")
    result = await client.complete(
        model, SYSTEM, prompt, schema=SCHEMA, images=[image], timeout=90
    )
    data = result.data or {}
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()
    if not content and not title:
        return "", result
    text = f"**{title}**\n{content}" if title else content
    return text.strip(), result
