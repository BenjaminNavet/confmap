# 0001 — LLM via la CLI Claude Code (abonnement) plutôt que l'API

## Contexte
L'utilisateur n'a pas de clé API Anthropic, seulement un abonnement Claude Code.

## Décision
Tous les appels LLM passent par `claude -p` en sous-processus :
`--model <id> --output-format json --tools "" --no-session-persistence --setting-sources "" --strict-mcp-config --disable-slash-commands --system-prompt … [--json-schema …]`.
- Sortie structurée : `--json-schema`, lue dans `structured_output`.
- Images : `--input-format stream-json` avec un bloc image base64.
- Coût : `total_cost_usd` renvoyé par la CLI (équivalent API) → événement `llm_usage`, cumul affiché en direct dans l'UI.
- Un backend API (`anthropic` SDK) reste possible derrière la même interface `LlmClient`, non implémenté en v1.

## Conséquences
- ~1 à 2 s de surcoût par appel (démarrage du processus) : la traduction est faite par petits lots (segments accumulés ~4 s) plutôt que segment par segment.
- Les appels consomment le quota de l'abonnement.
- Dépend de la présence de `claude` dans le PATH et d'une session connectée.
