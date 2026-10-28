# 0004 — Backend OpenRouter, choix des modèles et du dossier des notes

## Contexte
Sans abonnement Claude Code, l'application ne pouvait pas tourner (ADR 0001). Sans Obsidian, les notes partaient dans un dossier « Obsidian Vault » imposé.

## Décision
- `OpenRouterClient` (`openrouter.py`) implémente `LlmClient` via l'API `chat/completions` : sortie structurée par `response_format` JSON Schema strict avec `provider.require_parameters`, images en `data:` URL, coût réel lu dans `usage.cost`.
- `[llm] backend = auto | claude | openrouter` ; `auto` préfère la CLI si `claude` est dans le PATH, sinon OpenRouter si `OPENROUTER_API_KEY` est définie.
- Défauts OpenRouter : `deepseek/deepseek-v4-pro` ; `deepseek/deepseek-v4.1-flash` pour la vision (Pro est texte seul).
- Modèle par étape, priorité : `config.toml` > choix dans l'interface (`preferences.json`, par backend) > défaut du backend. `settings.models` est modifié en place, donc un changement vaut dès l'appel suivant.
- Le prix affiché à la sélection vient du catalogue public OpenRouter (sans clé, en cache une heure, seulement les modèles avec `structured_outputs`). Le coût cumulé vient toujours des réponses, jamais d'une table de prix locale.
- Dossier des notes : `config.toml` > choix dans l'interface > vault Obsidian par défaut si `obsidian.json` existe ; sinon une session ne peut pas démarrer avant le choix.

## Conséquences
- Un modèle sans sortie structurée n'apparaît pas dans la liste ; tapé à la main, il peut échouer.
- `preferences.json` (non versionné) contient les choix de l'interface.
