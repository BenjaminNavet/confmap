# confmap

Suivre une conférence en salle depuis un ordinateur portable (macOS ou Windows) :

- **transcription en direct** de n'importe quelle langue (Whisper local : mlx-whisper sur puce Apple, faster-whisper sur Windows/Linux) **traduite en français** ;
- **carte des idées** qui se construit au fil de la présentation (sujets côte à côte : processus, chronologie, concept, comparaison) ;
- **notes** tapées sur l'ordinateur ou l'iPhone, **photos de slides** prises sur l'iPhone et analysées (seul le texte extrait est gardé) ;
- **coût équivalent API** affiché en direct ;
- en fin de session, une **note Markdown** (résumé, carte Mermaid, notes et slides, transcription bilingue) et un **`.canvas`**, prêts pour Obsidian mais lisibles sans.

Les appels au LLM passent soit par la CLI Claude Code (abonnement), soit par [OpenRouter](https://openrouter.ai) (clé API, paiement à l'usage) : voir [LLM : Claude Code ou OpenRouter](#llm--claude-code-ou-openrouter).

## Prérequis

- macOS sur puce Apple, ou Windows 10/11 (Linux fonctionne aussi).
- [`uv`](https://docs.astral.sh/uv/), `ffmpeg` (seulement pour rejouer des fichiers non WAV ; Windows : `winget install ffmpeg`).
- **Au choix** : Claude Code installé et connecté (`claude` dans le PATH ; sous Windows, préférer l'installateur natif, qui fournit `claude.exe`), **ou** une clé OpenRouter.
- Au premier lancement, les modèles Whisper sont téléchargés depuis Hugging Face (~1,6 Go pour le direct, ~3 Go pour la finalisation).

Le moteur Whisper est choisi automatiquement : mlx-whisper (GPU Metal) sur Mac Apple Silicon, faster-whisper ailleurs (GPU NVIDIA via CUDA s'il est présent, sinon CPU). Sur un PC sans GPU NVIDIA, `large-v3-turbo` peut prendre du retard en direct : confmap passe alors seul au modèle de secours (`small`) ; on peut aussi fixer `whisper_live = "small"` dans `config.toml`.

## Lancer

```bash
cd confmap
uv sync
cp config.example.toml config.toml   # optionnel : modèles, vault, port
uv run confmap serve
```

Puis ouvrir <http://localhost:8010>.

Au premier lancement sans Obsidian, ouvrir **⚙ Réglages** sur l'accueil pour choisir le dossier des notes.

**Lancement depuis Spotlight** : `./scripts/install_app.sh` crée `~/Applications/confmap.app`. Taper « confmap » dans Spotlight démarre le serveur s'il ne tourne pas (journal : `~/Library/Logs/confmap.log`) et ouvre la page. Au premier enregistrement, macOS demande l'autorisation d'utiliser le micro pour le terminal.

**Lancement depuis le menu Démarrer (Windows)** : `powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1` crée un raccourci « confmap ». Il démarre le serveur en arrière-plan s'il ne tourne pas (journal : `%LOCALAPPDATA%\confmap\confmap.log`) et ouvre la page. Vérifier dans *Paramètres → Confidentialité → Microphone* que les applications de bureau ont accès au micro. Pour que l'iPhone joigne le PC, autoriser Python dans le pare-feu Windows (réseau privé) à la première demande.

1. **● Nouvelle session** : l'enregistrement démarre. Saisir titre et orateur en haut (ils améliorent traduction et carte).
2. **📱** : QR code à scanner avec l'iPhone → page pour prendre des photos de slides et envoyer des notes.
   Si le wifi de la conférence isole les appareils, connecter l'ordinateur au partage de connexion de l'iPhone.
3. **⚡** force une mise à jour de la carte ; **⤢** tout voir ; **↻ Tidy** réorganiser ; **📄 Source** ce qui a produit les derniers ajouts. La transcription est en deux colonnes alignées (original | français) ; survoler un passage surligne sa traduction, le cliquer surligne les boîtes de la carte qui en viennent.
4. **■ Fin** (deux clics) : re-transcription complète, re-traduction, résumé, écriture dans le vault. La fenêtre peut être fermée pendant ce temps.

Une session interrompue (crash, fermeture) se rouvre depuis l'accueil : **▶ Reprendre** relance l'enregistrement dans un nouveau fichier.

## LLM : Claude Code ou OpenRouter

Traduction, carte, lecture des photos de slides et résumé font appel à un LLM. Deux backends :

| | Claude Code (`claude`) | OpenRouter |
|---|---|---|
| Accès | abonnement Claude (Pro/Max) | clé API, crédits prépayés |
| Modèles par défaut | Claude Haiku (traduction), Claude Sonnet (le reste) | DeepSeek V4 Pro ; DeepSeek V4.1 Flash pour les photos (DeepSeek Pro ne lit pas les images) |
| Autres modèles | modèles Claude | tous les modèles d'OpenRouter qui gèrent la sortie JSON structurée (Claude, GPT, Gemini, Mistral…) |
| Coût affiché | équivalent API calculé par la CLI (décompté du quota de l'abonnement) | coût réellement facturé, renvoyé par OpenRouter à chaque appel |

**Sans Claude Code** :

1. Créer un compte sur <https://openrouter.ai>, ajouter des crédits et générer une clé (*Keys*).
2. Créer un fichier `.env` à la racine du projet :
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
3. Lancer `uv run confmap serve` comme d'habitude.

Par défaut (`[llm] backend = "auto"`), confmap utilise Claude Code si `claude` est dans le PATH, sinon OpenRouter si la clé est définie. Pour forcer un backend, mettre `backend = "openrouter"` ou `"claude"` dans `config.toml`.

**Choisir les modèles** : accueil → **⚙ Réglages** → *Modèles*. Chaque étape (traduction, carte, photos, résumé) a son propre modèle, à choisir dans la liste ou en tapant un identifiant OpenRouter (`openai/gpt-5`, `google/gemini-3-flash`…). Le prix par million de tokens (entrée / sortie) s'affiche sous chaque modèle, d'après le catalogue public d'OpenRouter. Le choix est enregistré dans `preferences.json`, séparément pour chaque backend, et sert dès l'appel suivant, même en pleine session. **Défaut** revient au modèle par défaut. Un modèle écrit dans `[models]` de `config.toml` passe avant tout et ne se change pas dans l'interface.

Le coût en haut de l'écran additionne le coût renvoyé par chaque appel : il suit donc le modèle utilisé à ce moment-là. Pour la photo de slide, choisir un modèle qui lit les images (l'interface signale ceux qui ne le font pas).

À titre indicatif, une heure de conférence coûte environ 3 $ avec Claude Sonnet pour la carte (appel toutes les 20 s) ; avec DeepSeek V4 Pro, le prix par token est environ trois fois plus bas en entrée et cinq fois plus bas en sortie. L'intervalle de la carte (`[map] interval_seconds`) est le principal levier de coût.

### Rejouer un fichier (démo, tests)

```bash
uv run confmap serve --audio-file conference.mp3 --speed 1
```

## Sorties

```
<vault>/2026-10-27 Titre/
  Titre.md        # frontmatter, Résumé, Carte (Mermaid + canvas intégré), Mes notes et slides, Transcription
  Titre.canvas
```

**Où vont les notes ?**

- Si Obsidian est installé (déjà lancé une fois sur la machine) : `~/Documents/Obsidian Vault/Conferences` par défaut.
- Sinon, l'accueil demande de choisir un dossier (**⚙ Réglages** → *Dossier des notes*, `~/Documents/confmap` proposé) avant la première session. Le choix est gardé dans `preferences.json` et se change au même endroit.
- `[paths] vault` dans `config.toml` passe avant tout.

Les fichiers sont du Markdown ordinaire : sans Obsidian, ils s'ouvrent dans n'importe quel éditeur (VS Code et Typora affichent aussi les diagrammes Mermaid). Le `.canvas` est au format ouvert [JSON Canvas](https://jsoncanvas.org) ; seul Obsidian l'affiche vraiment, ailleurs c'est un fichier JSON.

L'audio et le journal de chaque session restent dans `sessions/<id>/`.

## Développement

```bash
uv run pytest -q
uvx ruff check --fix src tests && uvx ruff format src tests
```

Docs : `docs/superpowers/specs/` (design), `docs/superpowers/plans/` (plan), `docs/decisions/` (ADR), `docs/wip/` (suivi).
