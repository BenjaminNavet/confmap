"""Traduction en français des segments, par petits lots (voir ADR 0001)."""

from __future__ import annotations

from dataclasses import dataclass

from confmap.llm import LlmClient, LlmResult

SYSTEM = """Tu traduis en français, en direct, la transcription automatique d'une conférence.
- Traduis fidèlement, dans un français naturel et précis ; garde le registre de l'orateur.
- La transcription est imparfaite (mots mal reconnus, phrases coupées) : corrige le sens évident sans inventer.
- Garde les termes techniques consacrés en anglais si c'est l'usage en français ; garde les noms propres, sigles, chiffres et unités.
- Utilise le CONTEXTE (titre, orateur, notes, slides) pour orthographier correctement les noms et le jargon ; un même terme est toujours traduit de la même façon.
- Le sens prime sur le mot à mot : attention aux négations et aux tournures (« far from complete » = « loin d'être complet »).
- Un segment déjà en français est seulement corrigé (ponctuation, mots mal reconnus).
- Réponds pour chaque id fourni, dans l'ordre, sans rien ajouter."""

SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "fr": {"type": "string"}},
                "required": ["id", "fr"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


@dataclass
class SegmentToTranslate:
    """Segment en attente de traduction."""

    id: str
    lang: str
    text: str


@dataclass
class TranslatedPair:
    """Couple original/traduction déjà produit (historique pour la cohérence)."""

    original: str
    french: str


def build_prompt(
    context: str, history: list[TranslatedPair], segments: list[SegmentToTranslate]
) -> str:
    """Construit le prompt d'un lot."""
    lines = [f"CONTEXTE : {context or '(aucun)'}", ""]
    if history:
        lines.append("DERNIERS SEGMENTS (pour la cohérence, ne pas retraduire) :")
        lines += [f"- {pair.original}\n  → {pair.french}" for pair in history]
        lines.append("")
    lines.append("À TRADUIRE :")
    lines += [f"[{segment.id}] ({segment.lang}) {segment.text}" for segment in segments]
    return "\n".join(lines)


async def translate_batch(
    client: LlmClient,
    model: str,
    context: str,
    history: list[TranslatedPair],
    segments: list[SegmentToTranslate],
    timeout: float = 45,
) -> tuple[dict[str, str], LlmResult]:
    """Traduit un lot ; retourne {id du segment: traduction} et la réponse brute."""
    result = await client.complete(
        model,
        SYSTEM,
        build_prompt(context, history, segments),
        schema=SCHEMA,
        timeout=timeout,
    )
    wanted = {segment.id for segment in segments}
    translations: dict[str, str] = {}
    for item in (result.data or {}).get("translations", []):
        segment_id = str(item.get("id", "")).strip("[] ")
        french = str(item.get("fr", "")).strip()
        if segment_id in wanted and french:
            translations[segment_id] = french
    # Si le modèle a renvoyé les traductions sans les bons ids, on les associe dans l'ordre.
    if not translations and len((result.data or {}).get("translations", [])) == len(
        segments
    ):
        for segment, item in zip(segments, result.data["translations"], strict=True):
            translations[segment.id] = str(item.get("fr", "")).strip()
    return translations, result
