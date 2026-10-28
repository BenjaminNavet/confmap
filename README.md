# confmap

Suivre une conférence en salle depuis un ordinateur portable (macOS ou Windows) :

- **transcription en direct** de n'importe quelle langue (Whisper local : mlx-whisper sur puce Apple, faster-whisper sur Windows/Linux) **traduite en français** ;
- **carte des idées** qui se construit au fil de la présentation (sujets côte à côte : processus, chronologie, concept, comparaison) ;
- **notes** tapées sur l'ordinateur ou l'iPhone, **photos de slides** prises sur l'iPhone et analysées (seul le texte extrait est gardé) ;
- **coût équivalent API** affiché en direct ;
- en fin de session, une **note Obsidian** (résumé, carte Mermaid, notes et slides, transcription bilingue) et un **`.canvas`** dans un vault dédié.

Les appels à Claude passent par la CLI Claude Code (abonnement), pas par une clé API (voir `docs/decisions/0001-llm-via-claude-code-cli.md`).

## Prérequis

- macOS sur puce Apple, ou Windows 10/11 (Linux fonctionne aussi).
- [`uv`](https://docs.astral.sh/uv/), `ffmpeg` (seulement pour rejouer des fichiers non WAV ; Windows : `winget install ffmpeg`).
- Claude Code installé et connecté (`claude` dans le PATH ; sous Windows, préférer l'installateur natif, qui fournit `claude.exe`).
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

**Lancement depuis Spotlight** : `./scripts/install_app.sh` crée `~/Applications/confmap.app`. Taper « confmap » dans Spotlight démarre le serveur s'il ne tourne pas (journal : `~/Library/Logs/confmap.log`) et ouvre la page. Au premier enregistrement, macOS demande l'autorisation d'utiliser le micro pour le terminal.

**Lancement depuis le menu Démarrer (Windows)** : `powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1` crée un raccourci « confmap ». Il démarre le serveur en arrière-plan s'il ne tourne pas (journal : `%LOCALAPPDATA%\confmap\confmap.log`) et ouvre la page. Vérifier dans *Paramètres → Confidentialité → Microphone* que les applications de bureau ont accès au micro. Pour que l'iPhone joigne le PC, autoriser Python dans le pare-feu Windows (réseau privé) à la première demande.

1. **● Nouvelle session** : l'enregistrement démarre. Saisir titre et orateur en haut (ils améliorent traduction et carte).
2. **📱** : QR code à scanner avec l'iPhone → page pour prendre des photos de slides et envoyer des notes.
   Si le wifi de la conférence isole les appareils, connecter l'ordinateur au partage de connexion de l'iPhone.
3. **⚡** force une mise à jour de la carte ; **⤢** tout voir ; **↻ Tidy** réorganiser ; **📄 Source** ce qui a produit les derniers ajouts. La transcription est en deux colonnes alignées (original | français) ; survoler un passage surligne sa traduction, le cliquer surligne les boîtes de la carte qui en viennent.
4. **■ Fin** (deux clics) : re-transcription complète, re-traduction, résumé, écriture dans le vault. La fenêtre peut être fermée pendant ce temps.

Une session interrompue (crash, fermeture) se rouvre depuis l'accueil : **▶ Reprendre** relance l'enregistrement dans un nouveau fichier.

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

Le vault par défaut est `~/Documents/Obsidian Vault/Conferences` (`[paths] vault` dans `config.toml`). L'audio et le journal de chaque session restent dans `sessions/<id>/`.

## Développement

```bash
uv run pytest -q
uvx ruff check --fix src tests && uvx ruff format src tests
```

Docs : `docs/superpowers/specs/` (design), `docs/superpowers/plans/` (plan), `docs/decisions/` (ADR), `docs/wip/` (suivi).
