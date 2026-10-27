# Juge itératif (UI + rendu Obsidian)

Boucle ≤ 5 itérations : capture (rejeu 90 s headless) → juge (agent neuf, cadre théorique injecté) → corrections → commit.

- Banc : `scripts/judge/capture.py <dossier>` (vault/sessions isolés dans `.judge/`, port 8011), extrait `.judge/extrait.wav`
  (session 01M5Y7940…, 30 s → 120 s).
- Cadre : `docs/judge/cadre-theorique.md` ; brief : `docs/judge/brief-juge.md`.
- Rapports : `.judge/iter-N/rapport.md` (non versionnés) ; scores reportés ci-dessous.

## Scores
| Itération | Score | Corrections |
|---|---|---|
| 1 | 46/90 (bloquant : stabilité carte) | carte stable + collisions, texte 17 px, paragraphe courant, canvas hiérarchique fromSide/toSide, transcription en callout, résumé horodaté et étiqueté, prompt Whisper |
| 2 | 52/84 (62 %) | placement par place libre la plus proche, cadrage du sujet courant (zoom ≥ 0,95), nœud neuf signalé 8 s, ≤ 8 nœuds/sujet, comparaison mieux détectée ; ADR 0002 |

## Prochaine étape
Itération 3 : capture puis juge.
