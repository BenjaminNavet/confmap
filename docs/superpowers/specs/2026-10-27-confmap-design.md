# confmap — design

Date : 2026-10-27 · Statut : validé en brainstorming, à relire

## 1. But

Suivre une conférence en salle depuis un MacBook :
- transcription en direct de n'importe quelle langue, traduite en français ;
- carte des idées qui se construit au fil de la présentation ;
- notes et photos (iPhone) ajoutées en cours de route et prises en compte immédiatement ;
- en fin de session, une note Obsidian (résumé succinct, carte, transcription brute bilingue) et un `.canvas`, dans un vault dédié.

Aucune solution existante ne couvre l'ensemble (recherche du 2026-10-27). La logique de carte s'inspire de [firdavz/lectra](https://github.com/firdavz/lectra) (`backend/services/topics.py`, `diagram.py`, `frontend/app.js`). Le dépôt n'a pas de licence : on réimplémente les idées, sans copier le code.

## 2. Contraintes et choix

| Sujet | Choix |
|---|---|
| Source audio | Micro du MacBook, orateur sur les enceintes de la salle |
| Traitement | Hybride : transcription locale, traduction/carte/vision/résumé via Claude |
| Transcription | `mlx-whisper` (`large-v3-turbo` en direct, `large-v3` en finalisation), langue détectée automatiquement |
| LLM | `claude-haiku-5-5` pour la traduction en direct ; `claude-sonnet-5-5` pour la carte, la vision, la re-traduction finale et le résumé. Les deux sont configurables. Appels via la CLI Claude Code (abonnement), voir ADR 0001 |
| Coût | Coût équivalent API de chaque appel (`total_cost_usd` de la CLI) cumulé et affiché en direct dans la barre du haut |
| Photos | Prises sur iPhone via une page web servie par le Mac ; seul le texte extrait est conservé, jamais l'image |
| Affichage transcription | Original (petit, grisé) + traduction française, phrase par phrase |
| Diagramme dans Obsidian | `.canvas` détaillé + Mermaid simplifié dans la note |
| Vault | Nouveau vault dédié, chemin configurable (défaut `~/Documents/Obsidian Vault/Conferences`) |
| Stack | Python + `uv`, FastAPI, WebSocket ; frontend HTML/JS sans étape de build, Cytoscape.js + cytoscape-dagre |
| Projet | `~/dev/confmap` |

Hors périmètre v1 : édition du texte des nœuds dans l'interface, plusieurs sessions simultanées, capture du son système, application native.

## 3. Architecture

```
 Micro Mac ──► AudioCapture ──► segments (VAD) ──► Transcriber (mlx-whisper)
                    │                                   │ segment {t0, t1, lang, texte}
                    └─► enregistrement.wav              ▼
 iPhone ──photo──► VisionAnalyzer ──► slide{texte} ──► SessionStore ◄── notes, contexte
                                                       │ (events.jsonl)
                          ┌────────────────────────────┼─────────────────┐
                          ▼                            ▼                 ▼
                   Translator (Haiku)          MapUpdater (Sonnet)   WebSocket → UI
                                                       │
                          fin de session ▼
                   Finalizer : re-Whisper → re-traduction → résumé → VaultWriter
```

### Principes
- **Journal d'événements, source unique.** `sessions/<id>/events.jsonl`, un événement par ligne, uniquement ajouté. Types : `context`, `segment`, `translation`, `note`, `slide`, `map_update`, `status`, `finalize_step`. L'UI se reconstruit en relisant le journal ; une session plantée se recharge sans perte.
- **Un module = une responsabilité**, avec entrée/sortie typées (Pydantic) et testables séparément : `audio_capture`, `transcriber`, `translator`, `vision`, `map_model` (logique pure), `map_updater` (appel LLM), `session_store`, `finalizer`, `vault_writer`, `web` (FastAPI/WS).
- **Contexte prioritaire.** Le titre et l'orateur (événement `context`, modifiable à tout moment) sont ajoutés aux prompts de traduction, de vision, de carte et de résumé. Une note ou une slide déclenche une mise à jour de la carte immédiate (sous réserve de l'écart minimal).
- **La capture audio se fait côté serveur** (`sounddevice`), indépendamment du navigateur : fermer l'onglet n'arrête pas l'enregistrement.

### Transcription en direct
- Audio 16 kHz mono, VAD (Silero) qui découpe en segments de 2 à 8 s sur les pauses (coupure forcée à 8 s).
- Chaque segment est transcrit par `mlx-whisper` (`large-v3-turbo`) dans un worker séparé ; latence visée de 3 à 6 s.
- Si le retard dépasse 15 s, bascule automatique vers `small` et alerte dans l'UI.

### Traduction en direct
- Chaque segment est traduit par Haiku en français. Le prompt contient le contexte et les 2 segments précédents (original + traduction) pour la cohérence.
- Un segment déjà en français n'est pas traduit (copie directe).

## 4. Carte des idées (modèle lectra)

### Modèle
- La carte est une liste de **topics** posés côte à côte de gauche à droite. Topic : `{id, title, kind, nodes[], edges[], started_at}`.
- `kind` ∈ `process` (de haut en bas), `timeline` (de gauche à droite, dates sur les flèches), `concept` (radial autour de l'idée principale), `comparison` (éléments comparés au-dessus de leurs caractéristiques).
- Nœud : `{id, label, emoji, sources[]}`, où `sources` liste les ids des segments, notes ou slides à l'origine du nœud. Lien : `{from, to, label}`.
- **Ajout seulement** : rien n'est renommé ni supprimé. Un topic est plein à 10 nœuds ou après 5 min ; la suite part dans un nouveau groupe et les topics terminés ne bougent plus.

### Mise à jour
- Boucle : toutes les 20 s, plus ⚡ manuel, plus déclenchement automatique sur note/slide ; écart minimal de 8 s entre deux appels.
- Prompt : titres des topics précédents, topic courant complet (nœuds + flèches), 400 derniers caractères déjà traités (contexte), puis le **nouveau contenu seulement**, où notes et slides sont marquées `[NOTE]` / `[SLIDE]`. Le contenu est envoyé en français (traductions).
- Règles reprises de lectra, adaptées : libellés en français, termes précis du domaine, 1 à 5 mots ; flèches = verbe court ; chaque flèche se lit comme une phrase vraie ; jamais de fait inventé ; au maximum 7 nouveaux nœuds par réponse ; réponse vide pour les passages sans contenu (salutations, logistique).
- Réponse structurée imposée par l'API (schéma JSON `{add, new_topic_title, new_topic_kind, new_topic}`), puis validation Pydantic et **merge tolérant** : un libellé déjà présent est réutilisé, et les flèches vers un nœud inconnu, les auto-boucles et les doublons sont ignorés.
- Pointeur « déjà traité » : il n'avance que si l'appel réussit. Timeout de 30 s, puis une nouvelle tentative.

### Rendu
- Cytoscape.js + dagre, mise en page par type (radiale maison pour `concept`). Seuls les topics modifiés sont réorganisés.
- Les nouveaux nœuds brillent pendant 4 s ; en mode suivi, la vue suit la croissance jusqu'à ce que l'utilisateur déplace la vue ; boutons ⤢, ↻ Tidy, 📄 Source (contenu à l'origine des derniers nœuds).

## 5. Interface

### Mac (`http://localhost:8010`)
- Barre du haut : champs titre et orateur, indicateur REC + durée, statuts Whisper et réseau (avec nombre d'éléments en attente), ⚡, ■ Fin.
- Panneau gauche : transcription bilingue qui défile seule (pause si l'utilisateur remonte) ; notes 📝 et slides 📷 insérées à leur moment avec un style distinct ; champ de note en bas (Entrée = envoyer).
- Panneau droit : carte ; bouton QR qui affiche le lien de la page iPhone.

### iPhone (`/capture?t=<jeton>`)
- Bouton 📷 (`<input type="file" accept="image/*" capture="environment">`, fonctionne en HTTP), champ note, liste des derniers envois avec statut (envoyé → analysé ✓).
- Jeton aléatoire par session, obligatoire sur toutes les routes d'envoi.
- Le serveur écoute sur le réseau local. Solution de repli si le wifi isole les appareils : le Mac se connecte au partage de connexion de l'iPhone.

### Analyse des photos
- Image redimensionnée (côté max 1568 px), envoyée à Sonnet avec le contexte et les 60 dernières secondes de traduction.
- Sortie : texte de la slide (titre, points, données chiffrées, références citées), en français, avec les termes techniques d'origine entre parenthèses. L'image est supprimée après analyse réussie.

## 6. Finalisation

Bouton ■ Fin → arrêt de l'enregistrement, puis étapes séquentielles. Chacune écrit un événement `finalize_step` et peut être reprise :
1. Re-transcription complète de `enregistrement.wav` (`large-v3`).
2. Re-traduction par lots d'environ 2000 mots (Sonnet), avec contexte et glossaire tiré des libellés de la carte. En cas d'échec, la note utilise les traductions du direct.
3. Résumé (Sonnet) à partir de la transcription finale, des notes, des slides et de la carte : 3 à 5 phrases, 3 à 6 points clés, questions ouvertes.
4. Écriture dans le vault. La carte n'est pas régénérée.

### Sortie dans le vault
```
<vault>/Conferences/2026-10-27 <Titre>/
  <Titre>.md
  <Titre>.canvas
```
- Note : frontmatter (`type: conference`, `titre`, `orateur`, `date`, `langue_source`, `duree`, `audio`, `tags`), puis sections `## Résumé`, `## Carte` (Mermaid `mindmap` des titres de topics + `![[<Titre>.canvas]]`), `## Mes notes et slides` (horodatées), `## Transcription` (paragraphes de 30 à 60 s : traduction française, puis original en citation italique, horodatage `[mm:ss]`).
- Canvas : un nœud texte par nœud de carte avec la position finale Cytoscape, une flèche libellée par lien, un groupe par topic (libellé = titre + icône de type).
- Pas d'écrasement : si le dossier existe, un suffixe ` (2)` est ajouté.
- L'audio reste dans `sessions/<id>/`, hors du vault ; il est référencé dans le frontmatter.

## 7. Gestion des erreurs

| Panne | Comportement |
|---|---|
| Réseau coupé | Whisper continue ; traduction, carte et photos en file d'attente avec reprise (backoff exponentiel, plafond 30 s) ; badge « Réseau ✗ (n en attente) » |
| Whisper en retard > 15 s | Bascule vers un modèle plus léger, alerte |
| Réponse LLM invalide | Merge tolérant ; au pire l'appel est ignoré et le pointeur n'avance pas |
| Crash | Reprise depuis `events.jsonl` + audio au redémarrage (liste des sessions non finalisées) |
| Micro absent / permission refusée | Erreur explicite dans la barre, la session reste ouverte |
| Échec d'une étape de finalisation | Arrêt sur l'étape, bouton « Reprendre la finalisation » |

## 8. Tests

- `map_model` : tests unitaires du merge, de « topic plein », des doublons et des flèches invalides (portage des 22 vérifications décrites par lectra).
- Pipeline : faux Whisper + faux Claude sur un WAV court → journal attendu, carte attendue, note écrite.
- `vault_writer` : sorties de référence (`.md`, `.canvas`) dans un dossier temporaire ; le `.canvas` produit est un JSON valide selon le format JSON Canvas 1.0.
- Recette manuelle : podcast anglais et espagnol joué sur une enceinte, photos d'écran depuis l'iPhone.

## 9. Configuration (`config.toml`)

```toml
[models]
translate = "claude-haiku-5-5"
map = "claude-sonnet-5-5"
vision = "claude-sonnet-5-5"
summary = "claude-sonnet-5-5"
whisper_live = "mlx-community/whisper-large-v3-turbo"
whisper_final = "mlx-community/whisper-large-v3-mlx"

[map]
interval_seconds = 20
min_gap_seconds = 8
max_nodes_per_topic = 10
max_topic_seconds = 300

[paths]
vault = "~/Documents/Obsidian Vault/Conferences"
sessions = "~/dev/confmap/sessions"

[server]
port = 8010
```
Pas de clé API : la CLI `claude` doit être installée et connectée (ADR 0001).

## 10. Lots de développement

1. Squelette : projet `uv`, FastAPI, config, `session_store` + journal, UI vide à deux panneaux.
2. Audio + VAD + mlx-whisper → transcription en direct dans le panneau gauche.
3. Traduction Haiku, contexte titre/orateur, notes.
4. Carte : `map_model` porté de lectra, `map_updater` Claude, rendu Cytoscape.
5. Page iPhone, QR code, jeton, analyse des photos.
6. Finalisation : re-transcription, re-traduction, résumé, `vault_writer` (`.md` + `.canvas`).
7. Robustesse : files d'attente réseau, reprise de session, bascule du modèle Whisper.
