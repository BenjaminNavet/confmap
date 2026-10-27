# confmap — suivi

**État** (2026-10-27) : tous les modules écrits (audio, VAD Silero ONNX, mlx-whisper, LLM via CLI Claude Code, traduction, carte, vision, finalisation, vault, web Mac + iPhone). Tests unitaires en cours d'écriture (agent). E2E réel sur audio TTS en cours.

**Prochaine étape** : résultats e2e → corrections ; test UI headless (playwright, `scratchpad/ui/ui_test.py`) ; recette robustesse (réseau coupé, reprise).

**Points ouverts**
- Latence réelle du direct à mesurer sur micro.
- Coût d'un appel CLI ≈ 1-2 s de démarrage : traduction par lots de 8 segments max.
