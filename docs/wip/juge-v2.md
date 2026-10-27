# Juge v2 (cadre réécrit de zéro)

Boucle ≤ 5 itérations : capture headless (même extrait 90 s) → juge neuf (cadre v2 injecté) → corrections → commit `wip:`.
Arrêt anticipé si le score plafonne ou régresse deux fois.

- Cadre : `docs/judge/v2/cadre.md` (grille A1…D4, /72) ; brief : `docs/judge/v2/brief.md`.
- Banc : `uv run --with playwright --with markdown python scripts/judge/capture.py .judge/v2-iter-N`.
- Rapports : `.judge/v2-iter-N/rapport.md` (non versionnés).

## Scores
| Itération | Score | Corrections |
|---|---|---|

## Prochaine étape
Itération 1 : capture en cours, puis juge.
