# confmap — suivi

**État** (2026-10-27) : v1 terminée et testée.
- 115 tests unitaires/intégration (fakes, sans réseau ni micro).
- E2E réel : audio → Whisper → Claude CLI → carte → note + canvas (EN), détection/traduction ES vérifiée.
- UI headless (Playwright) : session, contexte, note, photo via page iPhone, finalisation, rechargement.
- Robustesse : kill -9 en pleine session → reprise → 2e fichier audio → finalisation OK. Origine/Host vérifiés (403 pour un autre site).

**Mesures** : retard du direct ~5–9 s ; coût équivalent ≈ 3 $/h (85 % carte Sonnet toutes les 20 s, réglable).

**Non testé en conditions réelles** : micro du MacBook en salle (autorisation micro macOS à accorder au terminal au premier lancement), iPhone réel sur le wifi d'une conférence, coupure réseau réelle (couverte seulement par tests avec faux client).

**Pistes v2** : intervalle de carte adaptatif pour réduire le coût, édition des nœuds dans l'UI, export PDF.

**Retours v1.1** (2026-10-27) : lancement Spotlight (`scripts/install_app.sh`), thème sombre, transcription en deux colonnes alignées par paragraphe (nouveau paragraphe après 4 s de pause, 1 min, ou une note/photo). Corrigé : le `~` du vault par défaut n'était pas développé (note écrite dans `./~/…`).

**Carte dans Obsidian** (2026-10-27) : le mindmap Mermaid (titres seuls, illisible) est remplacé par un `flowchart` par sujet (nœuds + flèches étiquetées, LR pour process/timeline, TD sinon) ; le canvas n'est plus intégré mais lié, ses sujets sont rangés en grille (≤ 3000 px de large) et les boîtes s'agrandissent pour les étiquettes longues.
