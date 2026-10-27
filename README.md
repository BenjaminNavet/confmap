# confmap

Suivre une conférence en salle depuis un MacBook :

- **transcription en direct** de n'importe quelle langue (Whisper local, sur puce Apple) **traduite en français** ;
- **carte des idées** qui se construit au fil de la présentation (sujets côte à côte : processus, chronologie, concept, comparaison) ;
- **notes** tapées sur le Mac ou l'iPhone, **photos de slides** prises sur l'iPhone et analysées (seul le texte extrait est gardé) ;
- **coût équivalent API** affiché en direct ;
- en fin de session, une **note Obsidian** (résumé, carte Mermaid, notes et slides, transcription bilingue) et un **`.canvas`** dans un vault dédié.

Les appels à Claude passent par la CLI Claude Code (abonnement), pas par une clé API (voir `docs/decisions/0001-llm-via-claude-code-cli.md`).

## Prérequis

- macOS sur puce Apple, [`uv`](https://docs.astral.sh/uv/), `ffmpeg` (seulement pour rejouer des fichiers non WAV).
- Claude Code installé et connecté (`claude` dans le PATH).
- Au premier lancement, les modèles Whisper sont téléchargés depuis Hugging Face (~1,6 Go pour le direct, ~3 Go pour la finalisation).

## Lancer

```bash
cd ~/dev/confmap
uv sync
cp config.example.toml config.toml   # optionnel : modèles, vault, port
uv run confmap serve
```

Puis ouvrir <http://localhost:8010>. Au premier enregistrement, macOS demande l'autorisation d'utiliser le micro pour le terminal.

1. **● Nouvelle session** : l'enregistrement démarre. Saisir titre et orateur en haut (ils améliorent traduction et carte).
2. **📱** : QR code à scanner avec l'iPhone → page pour prendre des photos de slides et envoyer des notes.
   Si le wifi de la conférence isole les appareils, connecter le Mac au partage de connexion de l'iPhone.
3. **⚡** force une mise à jour de la carte ; **⤢** tout voir ; **↻ Tidy** réorganiser ; **📄 Source** ce qui a produit les derniers ajouts. Cliquer un passage de la transcription surligne les boîtes qui en viennent.
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
