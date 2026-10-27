# confmap — plan d'implémentation

Spec : `docs/superpowers/specs/2026-10-27-confmap-design.md` (à lire avant tout lot).
Suivi : `docs/wip/confmap.md` (état, prochaine étape), mis à jour à chaque commit `wip:`.

## Règles communes à tous les lots

- Python ≥ 3.12, `uv`, `src/` layout ; `uvx ruff check --fix` + `uvx ruff format` sur les fichiers modifiés avant chaque commit.
- Tests : `uv run pytest -q`. Aucun test ne touche le réseau, le micro ou mlx : faux objets injectés.
- Commits : `git commit -m … -- <chemins>` (jamais `-a`). Un commit par tâche qui passe les tests.
- Docstrings Google, noms explicites. Pas de code copié de lectra (pas de licence) : on réimplémente à partir de la spec.
- Toute décision non évidente prise en cours de route → ADR `docs/decisions/NNNN-titre.md`.

## Structure cible

```
confmap/
  pyproject.toml            # deps + config ruff (CLAUDE.md global) + script `confmap`
  config.example.toml
  .env.example              # ANTHROPIC_API_KEY=
  src/confmap/
    config.py               # chargement config.toml → modèles Pydantic
    events.py               # schéma des événements (union discriminée)
    session_store.py        # sessions/<id>/ : events.jsonl, audio, état
    bus.py                  # pub/sub asyncio : store → abonnés (WS, workers)
    audio_capture.py        # sounddevice → frames 16 kHz + enregistrement.wav
    segmenter.py            # VAD → segments 2–8 s
    transcriber.py          # mlx-whisper (worker thread unique)
    llm.py                  # client Anthropic : sortie structurée, timeout, retry, file hors ligne
    translator.py
    map_model.py            # logique pure de la carte (topics, merge)
    map_updater.py          # prompt + boucle de mise à jour
    vision.py
    finalizer.py
    vault_writer.py         # .md + .canvas
    web/app.py              # FastAPI : REST, WebSocket, page iPhone, QR
    web/static/{index.html, app.js, map.js, styles.css, capture.html}
    cli.py                  # `confmap serve`
  tests/
```

## Contrats partagés (figés au lot 1)

### Événements (`events.py`)
Chaque événement : `{id: str (ulid), session_id, ts: float (secondes depuis le début de la session), type, ...}`.

| type | champs |
|---|---|
| `context` | `title`, `speaker` |
| `segment` | `t0`, `t1`, `lang`, `text`, `final: bool` (false = direct, true = finalisation) |
| `translation` | `segment_id`, `text_fr` |
| `note` | `text`, `origin: "mac" \| "iphone"` |
| `slide` | `photo_id`, `text_fr`, `status: "pending" \| "done" \| "error"` |
| `map_update` | `topics` (snapshot complet), `added_node_ids`, `source_ids` |
| `status` | `component: "audio" \| "whisper" \| "network" \| "llm"`, `state`, `detail`, `pending: int` |
| `finalize_step` | `step: "retranscribe" \| "retranslate" \| "summary" \| "write"`, `state: "running" \| "done" \| "error"`, `detail`, `output_path?` |

### API HTTP
- `POST /api/sessions` → crée et démarre une session (capture audio lancée) → `{id, capture_url}`
- `GET /api/sessions` → liste (avec `finalized: bool`)
- `POST /api/sessions/{id}/context` `{title, speaker}`
- `POST /api/sessions/{id}/notes` `{text}` (jeton requis si origine iPhone)
- `POST /api/sessions/{id}/photos` multipart `file` + `?t=<jeton>`
- `POST /api/sessions/{id}/map/force`
- `POST /api/sessions/{id}/stop` → arrête la capture et lance la finalisation
- `POST /api/sessions/{id}/finalize` → (re)lance la finalisation depuis la dernière étape non terminée
- `GET /api/sessions/{id}/qr.svg`
- `WS /ws/{id}` : à la connexion, le serveur envoie `{"type":"snapshot","events":[…]}`, puis chaque nouvel événement tel quel. Le WebSocket est en lecture seule ; toutes les actions passent par REST.
- `GET /capture?s=<id>&t=<jeton>` → page iPhone

---

## Lot 1 — Squelette (exécutant : Sonnet)

1. `pyproject.toml` : dépendances `fastapi`, `uvicorn[standard]`, `pydantic`, `python-ulid`, `anthropic`, `sounddevice`, `numpy`, `soundfile`, `mlx-whisper`, `qrcode`, `python-multipart`, `python-dotenv` ; dev : `pytest`, `pytest-asyncio`, `httpx`. Ruff selon le CLAUDE.md global. Script `confmap = "confmap.cli:main"`.
2. `config.py` + `config.example.toml` (contenu de la spec §9) ; `~` développé ; tests.
3. `events.py` (tableau ci-dessus) + tests de sérialisation aller-retour.
4. `session_store.py` : `create()`, `list()`, `load(id)`, `append(event)` (écrit une ligne JSON + flush), `replay(id) -> list[Event]`, jeton aléatoire par session (`secrets.token_urlsafe(16)`) stocké dans `session.json`. Tests : ajout puis relecture, ligne tronquée en fin de fichier ignorée.
5. `bus.py` : `subscribe() -> asyncio.Queue`, `publish(event)` ; le store publie après chaque ajout.
6. `web/app.py` + `static/index.html` : layout deux panneaux vide, barre du haut, WS qui affiche les événements bruts. Routes REST `sessions`, `context`, `notes` (sans traitement). Test `httpx` : créer session → POST note → l'événement arrive dans le snapshot WS.
7. `cli.py` : `confmap serve` (uvicorn sur `0.0.0.0:<port>`).

**Fini quand** : `uv run confmap serve`, ouvrir localhost:8010, saisir titre + note → visibles dans le panneau ; tests verts. Commit `feat: squelette`.

## Lot 2 — Audio et transcription en direct (exécutant : Opus)

1. `audio_capture.py` : `sounddevice.InputStream` 16 kHz mono float32, callback → `asyncio.Queue` via `loop.call_soon_threadsafe` ; écriture continue dans `enregistrement.wav` (`soundfile`, flush régulier) ; événement `status(audio)` en cas d'erreur ou de permission refusée.
2. `segmenter.py` : VAD Silero. Vérifier au début que le paquet ne force pas `torch` ; sinon utiliser le modèle ONNX via `onnxruntime`. ADR si choix différent de la spec. Segments 2–8 s, coupure forcée à 8 s, padding 200 ms. Tests sur WAV synthétiques (silence/bruit/sinusoïde) avec VAD factice.
3. `transcriber.py` : un seul thread worker (mlx n'est pas fait pour des appels concurrents) ; `transcribe(samples) -> (lang, text)` ; mesure du retard (fin du segment → fin de transcription) ; au-delà de 15 s pendant 3 segments, bascule `whisper_live` → `small` + `status(whisper)`. Interface injectable pour les tests.
4. Câblage dans la session : capture → segmenter → transcriber → `segment`. Ignorer les segments vides ou hallucinations connues de Whisper (« Sous-titres réalisés par… », « Thank you for watching »).
5. Front : panneau gauche affiche les segments (original seul pour l'instant), défilement auto avec pause si l'utilisateur remonte.

**Fini quand** : une vidéo anglaise jouée sur le haut-parleur apparaît dans le panneau avec 3–6 s de retard ; `enregistrement.wav` lisible. Commit `feat: transcription en direct`.

## Lot 3 — LLM, traduction, notes (exécutant : Sonnet)

1. `llm.py` : client `anthropic.AsyncAnthropic`. Avant d'écrire, consulter le skill `claude-api` pour la syntaxe actuelle des sorties structurées et de la vision. Fonctions `complete_text(model, system, messages)` et `complete_json(model, system, messages, schema) -> dict`. Timeout 30 s, 1 nouvelle tentative ; erreurs réseau → `NetworkUnavailable` (la file d'attente viendra au lot 7). Un appel = un log (modèle, durée, tokens).
2. `translator.py` : prompt avec le contexte (titre, orateur), les 2 derniers couples original/traduction et le segment ; segment `lang == "fr"` copié tel quel ; événement `translation`.
3. Contexte : `POST context` → événement `context` ; le dernier contexte est injecté dans tous les prompts (helper `current_context(session)`).
4. Front : affichage bilingue (original petit et grisé, FR en dessous) ; notes 📝 insérées à leur `ts` ; champ de note (Entrée = envoyer).
5. Tests : faux client LLM ; vérifier le contenu du prompt (contexte présent, historique de 2 segments) et le passage direct du français.

**Fini quand** : traduction FR sous chaque segment en direct ; le nom de l'orateur saisi est bien orthographié dans les traductions. Commit `feat: traduction et notes`.

## Lot 4 — Carte des idées (exécutant : Sonnet pour 4.1–4.2, Opus pour 4.3–4.5)

1. `map_model.py` (pur, sans I/O) : modèles `MapNode`, `MapEdge`, `MapGraph`, `MapUpdate`, `Topic` ; `is_full(topic, now)`, `apply_update(topics, update, now) -> added_ids`, merge tolérant (libellé normalisé déjà présent → réutilisé ; flèche vers id inconnu, auto-boucle, doublon → ignorée ; libellé tronqué à 60 caractères ; emoji validé) ; topic plein → la suite va dans un nouveau topic `Titre (2)` du même type. `sources` des nœuds = ids des événements fournis.
2. Tests unitaires `map_model` (au moins 20 cas) : carte vide, ajout simple, doublon de libellé, flèche vers nœud existant par id de carte, flèche invalide, topic plein par nœuds puis par durée, numéro recopié dans le titre (« 2. Titre »), type inconnu → `process`.
3. `map_updater.py` : construction du prompt (spec §4 : titres précédents, topic courant, 400 caractères de contexte, nouveau contenu avec `[NOTE]`/`[SLIDE]`), schéma JSON, règles de rédaction en français ; boucle : intervalle 20 s, écart minimal 8 s, déclenchement par `force`, note ou slide ; pointeur « déjà traité » (id du dernier événement intégré) qui n'avance qu'en cas de succès ; événement `map_update`.
4. Réglage du prompt sur 2 transcriptions réelles (une conf technique EN, une FR) : sortie lisible, pas de boîtes vides de sens. Garder les transcriptions de test dans `tests/fixtures/`.
5. Front `map.js` : Cytoscape + cytoscape-dagre (versions exactes épinglées depuis cdnjs/jsdelivr) ; un groupe (compound node) par topic, posés de gauche à droite ; mise en page par type (dagre TB/LR, radiale pour `concept`) ; seuls les topics modifiés sont réorganisés ; brillance 4 s ; mode suivi ; boutons ⤢, ↻ Tidy, 📄 Source, ⚡. La position finale des nœuds est renvoyée au serveur (`POST /api/sessions/{id}/map/positions`) pour l'export `.canvas`.

**Fini quand** : sur une conférence YouTube de 15 min jouée sur le haut-parleur, la carte grandit en 3+ topics lisibles, une note tapée apparaît dans la carte à la mise à jour suivante. Commit `feat: carte des idées`.

## Lot 5 — iPhone et photos (exécutant : Sonnet)

1. `capture.html` : responsive, gros bouton 📷 (`<input type=file accept=image/* capture=environment>`), champ note, liste des envois avec statut (polling ou WS).
2. Routes `photos` et `notes` avec vérification du jeton (403 sinon) ; taille max 15 Mo ; image stockée temporairement dans `sessions/<id>/photos/`.
3. `vision.py` : redimensionnement (côté max 1568 px, Pillow), prompt (contexte + 60 dernières secondes de traduction) → texte de la slide en FR avec termes d'origine entre parenthèses ; événement `slide` pending → done ; suppression de l'image après succès ; déclenche une mise à jour de la carte.
4. `qr.svg` : URL `http://<ip-lan>:<port>/capture?s=…&t=…` (IP détectée via socket UDP vers 8.8.8.8, sans envoi) ; bouton QR dans l'UI Mac.
5. Tests : jeton invalide → 403 ; image redimensionnée ; slide pending → done avec faux LLM ; image supprimée.

**Fini quand** : photo d'une slide prise sur l'iPhone → texte 📷 dans la transcription en moins de 15 s et nœuds ajoutés à la carte si pertinent. Commit `feat: capture iPhone et analyse des photos`.

## Lot 6 — Finalisation et vault (exécutant : Sonnet)

1. `vault_writer.py` (pur, prend des données, écrit des fichiers) : note `.md` (frontmatter, Résumé, Carte avec Mermaid `mindmap` des titres de topics + embed canvas, Mes notes et slides, Transcription en paragraphes de 30 à 60 s FR + original en citation italique, `[mm:ss]`) ; `.canvas` JSON Canvas 1.0 (nœuds texte avec positions, flèches libellées, un groupe par topic) ; nom de dossier `YYYY-MM-DD <Titre>` assaini, suffixe ` (2)` si existant.
2. Tests de référence `vault_writer` (fixtures `.md`/`.canvas` attendus), validation de la structure JSON Canvas.
3. `finalizer.py` : étapes `retranscribe` (mlx-whisper `whisper_final` sur le WAV complet, segments `final: true`), `retranslate` (lots d'environ 2000 mots, glossaire = libellés de la carte ; repli sur traductions du direct), `summary`, `write` ; chaque étape écrit `finalize_step` et la reprise saute les étapes `done`.
4. Front : écran de progression après ■ Fin, lien `obsidian://open?path=…` vers la note à la fin (ouvert seulement sur clic, jamais automatiquement).
5. Tests : finalisation complète avec faux whisper/LLM dans un vault temporaire ; reprise après échec simulé à `summary`.

**Fini quand** : ■ Fin → note et canvas dans le vault, le canvas s'ouvre correctement dans Obsidian. Commit `feat: finalisation vers Obsidian`.

## Lot 7 — Robustesse (exécutant : Opus)

1. File d'attente hors ligne dans `llm.py` : traductions, mises à jour de carte et photos mises en attente sur `NetworkUnavailable`, reprise avec backoff (1 → 30 s), ordre conservé ; `status(network)` avec `pending`.
2. Reprise de session : au démarrage, lister les sessions non finalisées ; « Reprendre » rejoue le journal (UI + état carte + pointeurs) et relance la capture dans un nouveau segment audio (`enregistrement-2.wav`, concaténé à la finalisation).
3. Bascule Whisper testée (retard simulé) ; retour au modèle initial non prévu en v1.
4. Recette complète : 45 min de podcast EN puis ES, wifi coupé 2 min au milieu, 3 photos, 5 notes, un crash simulé (`kill`) puis reprise ; noter les problèmes dans `docs/wip/confmap.md`.

**Fini quand** : la recette passe sans perte de contenu. Commit `feat: robustesse hors ligne et reprise`.

---

## Ordre et parallélisme

Lot 1 d'abord : il fige les contrats. Ensuite les lots 2, 3 et 4.1–4.2 peuvent avancer en parallèle (worktrees séparés), car ils ne partagent que `events.py`. Les lots 4.3+, 5, 6 et 7 se font en séquence.
