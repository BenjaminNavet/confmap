# 0002 — Carte en direct stable, canvas exporté en disposition hiérarchique

## Contexte
Le juge itératif (docs/judge) a relevé deux exigences contradictoires : en direct, la carte ne doit
pas se réorganiser sous les yeux de l'auditeur (préservation de la carte mentale) ; à la révision,
le canvas Obsidian doit être lisible (niveaux, pas de croisements, pas de chevauchements).
Les positions du direct, issues d'ajouts successifs, ne sont pas une bonne disposition finale.

## Décision
- En direct : un nœud affiché ne bouge plus. Les nouveaux sont placés près de leurs voisins puis
  déplacés vers la place libre la plus proche. Seul « Tidy » réorganise. Zoom de suivi ≥ 0,95
  (texte ~14 px) : on cadre le sujet courant s'il tient, sinon on centre sur les ajouts.
- À l'export : le canvas recalcule une disposition hiérarchique par sujet (niveaux BFS, fromSide/toSide)
  sans reprendre les positions du direct.

## Conséquences
Le canvas ne ressemble pas exactement à la carte vue en salle ; c'est assumé (révision ≠ suivi en direct).
Les positions envoyées par l'app (`positions`) ne servent plus qu'au rechargement de la page.
