"""Prompt et appel LLM qui font grandir la carte des idées (modèle inspiré de lectra)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from confmap.llm import LlmClient, LlmError, LlmResult
from confmap.map_model import UPDATE_JSON_SCHEMA, MapUpdate, describe_map

MAX_NEW_CONTENT_CHARS = 8000
COVERED_TAIL_CHARS = 400

SYSTEM = """Tu construis en direct la carte des idées d'une conférence, pour un chercheur qui la suit.
La carte est découpée en SUJETS ; chaque sujet est un petit diagramme de boîtes reliées par des flèches, d'un des quatre types ci-dessous.
Le contenu vient d'une transcription automatique traduite en français (erreurs possibles), de NOTES de l'auditeur ([NOTE]) et du texte de SLIDES photographiées ([SLIDE]).
Les notes et slides sont fiables et prioritaires : utilise-les pour corriger les noms et préciser les idées.

Tu reçois la CARTE ACTUELLE, la fin de ce qu'elle COUVRE DÉJÀ (contexte seulement) et le NOUVEAU CONTENU.
Ajoute ce que le NOUVEAU CONTENU apporte. Ne répète, ne renomme, ne réécris jamais ce qui est déjà sur la carte.

Types de sujet — choisis celui qui correspond à la façon dont l'orateur expose :
- "process" : comment quelque chose fonctionne ou pourquoi il arrive : étapes, causes et effets. Boîtes = choses ou étapes ; flèches = verbes courts. Ex. : Données brutes → nettoyées par → Pipeline → produit → Graphe.
- "timeline" : événements dans l'ordre : historique, étapes d'un projet. Boîtes = événements courts commençant par un verbe ; flèche = « puis » ou une date (« en 2019 »). Les dates vont sur les flèches.
- "concept" : une idée principale et ses parties, types, propriétés ou exemples : définition, méthode, domaine. Une boîte centrale ; toutes les autres s'y rattachent directement ou indirectement. Flèches : comprend, est un type de, utilise, mesure, a pour exemple.
- "comparison" : deux choses ou plus comparées. Structure attendue : au moins DEUX boîtes « têtes » (les éléments comparés, ex. « 2018 » et « 2026 », « méthode A » et « méthode B »), chacune reliée à ses propres attributs ; chaque flèche va d'une tête vers une de ses caractéristiques ; une caractéristique commune reçoit une flèche de chaque tête. Une comparaison à une seule tête est invalide : crée l'autre tête.
Structures : comparison = têtes + attributs ; timeline = événements ordonnés reliés par « puis » ; process = étapes enchaînées ; concept = un hub central + satellites.
Choisis "comparison" dès que l'orateur oppose deux choses, deux versions ou deux moments (avant / maintenant, 2018 / 2026, méthode A / méthode B), même brièvement ; "timeline" dès qu'il raconte des étapes datées.

Règles de rédaction :
1. Une boîte = 1 à 5 mots, en français, termes précis du domaine (garde le terme anglais consacré si c'est l'usage : « embedding », « transformer »). Pas de phrase.
2. Une flèche = un verbe ou groupe verbal de 1 à 3 mots, sans virgule ni phrase (« adopté par », « remplace », « mène à », « utilise », « s'oppose à »), ou « puis » / une date dans une timeline. Jamais « est » seul, jamais de proposition complète : si aucun verbe précis ne convient, laisse "".
3. Lis chaque flèche comme une phrase : [boîte source] [flèche] [boîte cible]. Elle doit être vraie et dite (ou clairement voulue) par l'orateur.
4. N'invente jamais de fait. Utilise les noms propres (méthodes, auteurs, jeux de données, chiffres clés) plutôt que des termes vagues.
5. emoji : un seul, seulement s'il représente clairement un objet concret ; sinon "". La plupart des boîtes n'en ont pas.

Règles de sujet :
6. Les boîtes du sujet en cours vont dans "add", dans le type du SUJET COURANT. Les flèches de "add" peuvent viser des boîtes existantes du sujet courant par leur id.
7. Si la carte est vide, si l'orateur passe à autre chose, ou si le SUJET COURANT est PLEIN, ouvre un nouveau sujet : "new_topic_title" (1 à 5 mots, différent des titres précédents), "new_topic_kind", et ses boîtes et flèches dans "new_topic" (flèches internes à "new_topic" seulement).
8. Renvoie tout vide pour un contenu qui n'apporte rien : salutations, logistique, remerciements, blagues, problèmes techniques.
9. Ids des nouvelles boîtes : courts ("a", "b", "c"), uniques dans ta réponse.
10. Au plus 5 nouvelles boîtes par réponse : seulement les idées importantes. Un sujet lisible a 4 à 8 boîtes.
11. Un nouveau sujet ne reprend pas comme boîte centrale une boîte d'un sujet précédent : s'il ne fait que détailler cette boîte, ajoute plutôt au sujet courant."""


@dataclass
class ContentItem:
    """Morceau de nouveau contenu (parole traduite, note ou slide)."""

    event_id: str
    kind: str  # "speech", "note", "slide"
    text: str


def format_content(items: list[ContentItem]) -> str:
    """Met en forme le nouveau contenu, notes et slides marquées."""
    parts = []
    for item in items:
        if item.kind == "note":
            parts.append(f"[NOTE] {item.text}")
        elif item.kind == "slide":
            parts.append(f"[SLIDE] {item.text}")
        else:
            parts.append(item.text)
    return "\n".join(parts)


def build_prompt(
    context: str,
    topics: list[dict],
    current_full: bool,
    covered_text: str,
    items: list[ContentItem],
) -> str:
    """Prompt complet d'une mise à jour."""
    new_content = format_content(items)[-MAX_NEW_CONTENT_CHARS:]
    covered_tail = covered_text[-COVERED_TAIL_CHARS:]
    return (
        f"CONTEXTE : {context or '(aucun)'}\n\n"
        f"{describe_map(topics, current_full)}\n\n"
        f'COUVRE DÉJÀ (contexte seulement) : "…{covered_tail}"\n\n'
        f'NOUVEAU CONTENU :\n"""\n{new_content}\n"""'
    )


async def request_update(
    client: LlmClient,
    model: str,
    context: str,
    topics: list[dict],
    current_full: bool,
    covered_text: str,
    items: list[ContentItem],
) -> tuple[MapUpdate, LlmResult]:
    """Demande au modèle ce qu'il faut ajouter à la carte."""
    prompt = build_prompt(context, topics, current_full, covered_text, items)
    result = await client.complete(
        model, SYSTEM, prompt, schema=UPDATE_JSON_SCHEMA, timeout=60
    )
    try:
        return MapUpdate.model_validate(result.data or {}), result
    except ValidationError as error:
        raise LlmError(f"mise à jour de carte invalide : {error}") from error
