# 0003 — Moteur Whisper selon la plateforme

## Contexte
mlx-whisper ne tourne que sur Mac Apple Silicon. Le projet doit aussi fonctionner sous Windows.

## Décision
`WhisperTranscriber` porte la logique commune (langue dominante, bascule vers le modèle de secours, amorce, thread unique). Deux moteurs :
- `MlxWhisperTranscriber` sur macOS arm64 ;
- `FasterWhisperTranscriber` ailleurs (CTranslate2 : CUDA si présent, sinon CPU int8).

`create_transcriber` choisit selon `sys.platform`/`platform.machine()` ; les noms de modèles par défaut suivent le même choix (`config.py`), et les dépendances utilisent des marqueurs d'environnement dans `pyproject.toml`.

Le prompt système de `claude -p` passe par `--system-prompt-file` : sous Windows, une longue chaîne multiligne en argument est tronquée ou mal découpée (wrapper `.cmd`, limite de 32 Ko).

## Conséquences
- Un `config.toml` avec des noms `mlx-community/...` ne marche pas sous Windows : laisser les modèles Whisper commentés pour les valeurs par défaut.
- Sur CPU, le direct peut prendre du retard avec `large-v3-turbo` ; la bascule existante vers `small` compense.
- La CI (`.github/workflows/tests.yml`) exécute les tests sous Windows, macOS et Linux.
