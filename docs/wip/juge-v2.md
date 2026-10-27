# Juge v2 (cadre réécrit de zéro)

Boucle ≤ 5 itérations : capture headless (même extrait 90 s) → juge neuf (cadre v2 injecté) → corrections → commit `wip:`.
Arrêt anticipé si le score plafonne ou régresse deux fois.

- Cadre : `docs/judge/v2/cadre.md` (grille A1…D4, /72) ; brief : `docs/judge/v2/brief.md`.
- Banc : `uv run --with playwright --with markdown python scripts/judge/capture.py .judge/v2-iter-N`.
- Rapports : `.judge/v2-iter-N/rapport.md` (non versionnés).

## Scores
| Itération | Score | Corrections |
|---|---|---|
| 1 | 46/72 (A 11, B 16, C 11, D 8) | carte (stabilité, colonnes, comparaison, masquage), UI (rattrapage, décor, contraste, libellés), note (Testez-vous, callouts, ancres) ; clignotement des encadrés photo corrigé |
| 2 | 49/72 (A 14, B 15, C 10, D 10) | en cours : arêtes, encodage du type par position, cadrage, masquage réversible, badge traduction, transcription figée, étiquettes d'arêtes, plan des sujets |

## Prochaine étape
Corrections de l'itération 2 en cours (3 lots : map.js / app.js+css / Python). Ensuite capture v2-iter-3. Reporté : correction de termes Whisper par l'utilisateur.
