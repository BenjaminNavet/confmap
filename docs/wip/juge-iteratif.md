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

## Prochaine étape
Itération 2 : capture puis juge.
