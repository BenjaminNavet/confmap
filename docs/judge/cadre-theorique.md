# Cadre théorique du juge de confmap

Ce document est lu par le « juge » (agent Claude) avant de critiquer confmap. Il n'est pas un cours : chaque principe est relié à un critère vérifiable sur l'application. La grille de score (0-3) est en section 4.

## 0. Contexte d'usage à garder en tête

- **Utilisateur** : doctorant, en salle, MacBook ouvert sur les genoux ou une table. Il **regarde surtout l'orateur et les slides projetés**, pas l'écran. Chaque coup d'œil sur confmap est une tâche secondaire de 1 à 3 s.
- **Charge simultanée** : écouter (souvent en langue non maternelle) + lire (transcription + traduction) + éventuellement taper une note ou photographier un slide. C'est un cas d'attention divisée sévère.
- **Deux temps** : (a) pendant la conférence, comprendre et retenir (UI en direct) ; (b) plus tard, réviser dans Obsidian (note + canvas). Un artefact peut réussir en (a) et échouer en (b), et inversement.
- **Contenus produits** : transcription Whisper en direct, traduction française alignée en deux colonnes, « carte des idées » incrémentale (sujets côte à côte : processus, chronologie, concept, comparaison), notes tapées, photos de slides (iPhone), note Obsidian finale (résumé, carte Mermaid, notes et slides, transcription bilingue), fichier `.canvas`.
- **Principe directeur** : l'application doit **réduire la charge extrinsèque** (tout ce qui n'aide pas à comprendre) et **favoriser la charge germane** (construction de schémas) sans jamais voler l'attention à l'orateur.

Trois surfaces à juger séparément : **UI en direct**, **note Obsidian**, **canvas**.

---

## 1. Théorie de l'apprentissage

### 1.1 Théorie de la charge cognitive (Sweller)

Mémoire de travail très limitée (environ 4 éléments nouveaux simultanément, quelques secondes sans répétition) ; mémoire à long terme illimitée, organisée en schémas. Trois types de charge, additives :

| Type | Définition | Ce que ça veut dire pour confmap |
|---|---|---|
| Intrinsèque | Complexité propre du contenu (interactivité des éléments) | Non réductible par l'UI ; on peut la **segmenter** (carte par sujets) |
| Extrinsèque | Imposée par la présentation | Bruit visuel, décalage, défilement, libellés longs, alertes inutiles : **à minimiser** |
| Germane (pertinente) | Effort de construction de schémas | Carte des idées, regroupement, notes personnelles : **à favoriser** |

Effets utiles au jugement :

- **Split-attention** : quand deux sources liées doivent être intégrées mentalement (texte d'un côté, image de l'autre), la charge augmente. *Applications* : photo de slide séparée de la note qui la commente ; carte d'idées séparée de la phrase de transcription qui l'a produite ; colonne original et colonne française non alignées ligne à ligne.
- **Redondance** : présenter la même information sous deux formes que le novice peut comprendre seule est nuisible. *Tension de confmap* : original + français est redondant pour un lecteur qui comprend l'anglais, mais utile pour un non-natif ; la carte répète en partie la transcription. Le critère est donc : **chaque surface apporte-t-elle un plus (structure, relation) et non une simple répétition ?** Effet d'**inversion d'expertise** (Kalyuga) : ce qui aide un novice gêne l'expert ; l'utilisateur est expert du domaine mais pas forcément de la langue. L'interface devrait permettre de masquer une colonne.
- **Effet transitoire** (Sweller, Ayres, Kalyuga 2011) : l'information orale ou animée disparaît ; si elle est longue et complexe, elle s'évanouit avant d'être traitée. La transcription en direct **transforme du transitoire en persistant** (atout) mais si elle défile trop vite, elle redevient transitoire. Critère : une phrase reste lisible assez longtemps ; les segments ne se réécrivent pas sous les yeux (flicker).
- **Segmentation et pré-entraînement** : découper en unités gérables ; fournir en amont les termes clés. *Applications* : glossaire de termes, noms propres et acronymes mis en évidence ; sujets de la carte comme segments.
- **Effet de modalité** : texte + narration visuel/auditif répartit la charge sur deux canaux ; mais du texte **en plus** d'une narration (sous-titres) concurrence la lecture des slides (canal visuel). Voir 1.2 et 1.8.

### 1.2 Apprentissage multimédia (Mayer) et sous-titres

Théorie cognitive de l'apprentissage multimédia : canaux visuel et auditif séparés, capacité limitée, traitement actif (sélectionner, organiser, intégrer). Trois objectifs : réduire le traitement **extrinsèque**, gérer le traitement **essentiel**, favoriser le traitement **génératif**. Les 12 principes usuels :

| Objectif | Principe | Test sur confmap |
|---|---|---|
| Extrinsèque | **Cohérence** : retirer le superflu | Aucun élément décoratif, icône, animation non porteuse de sens |
| | **Signalement** : mettre en évidence l'organisation | Termes clés, changement de sujet, nouveau nœud visibles |
| | **Redondance** : pas de texte en plus d'un récit déjà compréhensible | Cf. 1.1 ; deux colonnes justifiées |
| | **Contiguïté spatiale** : mots et images liés proches | Photo de slide à côté de la note/du segment correspondant |
| | **Contiguïté temporelle** : présentés ensemble | Traduction apparaît avec/juste après l'original (latence faible) |
| Essentiel | **Segmentation** | Carte par sujets, note par sections |
| | **Pré-entraînement** | Termes et plan en tête de note |
| | **Modalité** : voix + image plutôt qu'image + texte | Ne pas surcharger le canal visuel pendant que l'orateur projette des slides |
| Génératif | **Multimédia** : mots + images > mots seuls | Carte + texte plutôt que texte seul |
| | **Personnalisation** : ton conversationnel | Peu pertinent ; ne pas pénaliser |
| | **Voix** et **Incarnation** | Non applicables |

*Remarque* : les principes de cohérence, signalement, segmentation, contiguïté et redondance sont les plus discriminants ici. Le nombre et la liste exacte (12 ou plus) varient selon les éditions : ne pas pinailler sur la liste, juger l'effet.

**Sous-titres en direct (travaux récents)** : l'équipe d'Anvers étudie les sous-titres intralinguistiques en direct (respeaking vs reconnaissance automatique) dans des cours en anglais pour étudiants non natifs, avec oculométrie et questionnaires de charge ; le pilote conclut que les étudiants ont moins profité des sous-titres que prévu (voir [S12]). Lecture pour confmap : le texte en direct **n'est pas gratuit** ; il coûte des fixations visuelles et son bénéfice dépend de la maîtrise de la langue, de la vitesse de l'orateur et de la qualité du texte. Le juge ne doit donc pas supposer que « plus de texte = mieux ».

### 1.3 Double codage (Paivio) et schémas

- **Double codage** : une information codée à la fois verbalement et visuellement/spatialement est mieux retenue (deux traces). La carte des idées et les photos de slides apportent le code visuel-spatial ; le texte apporte le verbal. *Critère* : la note finale et le canvas conservent **les deux codes liés** (carte + texte + slide) et pas seulement la transcription.
- **Organiseurs avancés** (Ausubel) et **schémas** : un cadre abstrait présenté avant/pendant facilite l'ancrage de détails. La carte des idées joue le rôle d'organiseur *émergent* ; le résumé en tête de note joue celui d'organiseur *a posteriori* (utile à la révision). *Critère* : la structure (processus, chronologie, concept, comparaison) correspond au **type de relation réellement exprimé** ; un schéma faux (chronologie là où il y a une comparaison) est pire que pas de schéma, car il induit un mauvais modèle mental.
- **Cartes conceptuelles** (Novak & Cañas) : concepts reliés par des **propositions** (concept - verbe de liaison - concept), hiérarchie du général au particulier, liens croisés. Une carte sans libellés de relation est un nuage de mots-clés, pas une carte conceptuelle.

### 1.4 Effet de génération et prise de notes

- **Effet de génération** : ce qu'on produit soi-même est mieux retenu que ce qu'on lit. Taper une note, même courte, est un acte génératif ; une note auto-générée par LLM ne l'est pas. Les notes manuscrites ou tapées sont utiles à la fois comme **encodage** (traiter en direct) et comme **stockage externe** (réviser).
- **Mueller & Oppenheimer (2014)** : la prise de notes sur ordinateur produirait plus de transcription verbatim et moins de compréhension conceptuelle. **Urry et al. (2021)** n'ont pas répliqué l'avantage du manuscrit pour le rappel conceptuel immédiat ; en revanche plus de mots notés allait avec de meilleurs scores et plus de recouvrement verbatim avec de moins bons [S10]. *Lecture* : le danger n'est pas le clavier, c'est la **transcription mécanique**. confmap fournit déjà la transcription : l'utilisateur doit être **libre de noter des idées, des questions, des liens**, pas de recopier. Critère : la saisie d'une note courte (idée + « ? ») est rapide et ne casse pas le flux.
- **NoTeeline** (Huq et al., 2025) : l'utilisateur tape des « micronotes » (mots-clés) pendant la vidéo, le LLM les développe en notes complètes selon son style ; amélioration de la couverture et de la rapidité du travail en direct vs notes entièrement automatiques [S6]. *Lecture* : l'intention de l'utilisateur doit **orienter** la synthèse ; une note finale qui ignore ce que le doctorant a tapé est un échec de personnalisation.
- **Notes de l'utilisateur vs génération par LLM** : marquer clairement la **provenance** (tapé par moi / généré / transcrit) dans la note Obsidian ; sinon l'utilisateur ne peut pas calibrer sa confiance, et le risque d'hallucination (nom, chiffre, attribution) devient invisible.

### 1.5 Récupération espacée et révision

- **Effet de test / pratique de récupération** (Roediger & Karpicke 2006) et **espacement** (Cepeda et al. 2006) : les deux stratégies à plus forte utilité d'après la synthèse de Dunlosky et al. (2013). Relire passivement est peu efficace.
- *Application* : la note Obsidian est le support de révision. Qualités attendues : **résumé court en tête** (récupération globale), questions ouvertes ou « à retenir » (amorces de récupération), possibilité de **masquer la traduction** pour s'entraîner (Obsidian : callouts repliables), liens vers d'autres notes de la vault pour reconsolider avec d'anciens schémas, date et orateur en frontmatter pour retrouver l'événement. La transcription bilingue complète est une **archive**, pas un support de révision : elle doit être repliée par défaut et ne doit pas noyer le résumé.

### 1.6 Attention divisée en direct

- L'attention divisée dégrade la compréhension et la mémorisation ; le **multitâche** réel est une commutation coûteuse. Écouter + lire + saisir sont trois tâches concurrentes sur la parole (phonologique) et la lecture (même boucle phonologique).
- La lecture de la traduction française **entre en compétition** avec l'écoute de l'orateur : il faut donc que l'UI soit **consultable à la demande** (glanceable) et non exigeante en continu.
- Corollaires pour les critères : limiter les événements qui attirent l'œil (pré-attentif : mouvement, clignotement, couleur vive) aux événements importants ; ne jamais déplacer ce que l'utilisateur lit ; la reprise après un coup d'œil ailleurs doit être facile (« où en étais-je ? » : ligne courante marquée, ancrage stable).

### 1.7 Charge propre à la traduction automatique

Latence de la traduction, erreurs de termes techniques, segmentation de phrases en cours de route (réécriture d'une traduction déjà lue) : chacun ajoute une charge de vérification. Un texte corrigé après coup sous les yeux du lecteur = effet transitoire inversé (le lecteur perd son repère). Critère : indicateur d'incertitude ou de provisoire sobre, et stabilité du texte une fois consolidé.

---

## 2. Visualisation

### 2.1 Tufte : encre-données et chartjunk

- **Ratio data-ink** : proportion d'encre utile à l'information. Supprimer tout ce qui n'encode rien (cadres, ombres, dégradés, bordures lourdes, grilles).
- **Chartjunk** : décor sans information ; la **densité informationnelle** reste souhaitable si elle est organisée. Attention : dans confmap en direct, la contrainte de glanceabilité (2.6, 3.4) limite la densité acceptable par rapport à un poster statique de Tufte.
- *Critères* : chaque pixel coloré a un sens ; pas de légende nécessaire pour décoder des couleurs décoratives ; le canvas Obsidian n'est pas encombré de nœuds vides ou d'arêtes redondantes.

### 2.2 Munzner : what / why / how

*What* (données : graphe en croissance, texte, images, temps), *why* (tâches : **résumer**, **retrouver**, **comparer**, **suivre l'évolution** ; en direct = monitoring, en différé = exploration et récupération), *how* (encodage : marques + canaux ; manipulation ; réduction).

- **Marques** : points (nœuds), lignes (arêtes), aires (conteneurs/enclosures). **Canaux** : position, taille, teinte, forme, orientation, mouvement. Efficacité des canaux (Cleveland & McGill, Mackinlay) : position > longueur > angle > aire > teinte/saturation. **Position ordonnée** pour la chronologie ; **teinte** pour catégories (peu de classes) ; **aires et contiguïté** pour appartenance.
- *Critères* : le type de sujet (processus, chronologie, concept, comparaison) est **encodé de façon distinctive** (disposition ou forme, pas seulement l'étiquette) ; un canal n'encode qu'une variable ; l'ordre temporel est lisible par la position ; un seul canal « fort » (ex. couleur vive) réservé à l'événement le plus important (le nouveau nœud, le sujet courant).
- Les « 3 questions » de Munzner : le juge se demande à chaque écran *quelle tâche cet écran sert-il ?* ; un écran qui sert plusieurs tâches contradictoires (monitoring en direct + exploration fine) est un défaut de conception.

### 2.3 Principes de la Gestalt

| Principe | Usage correct | Violation observable |
|---|---|---|
| Proximité | Nœuds d'un même sujet proches, espace net entre sujets | Deux sujets distincts séparés par moins d'espace que les nœuds d'un même sujet |
| Similarité | Même forme/couleur = même rôle | Même couleur pour deux rôles différents ; rôle identique avec styles variables |
| Continuité | Arêtes lisibles comme courbes continues ; flèches de processus alignées | Arêtes en zigzag, directions contradictoires dans une séquence |
| Enclosure / région commune | Cadre ou fond pour un sujet | Cadre autour d'éléments sans lien ; cadres imbriqués au-delà de 2 niveaux |
| Clôture, figure/fond | Sujet perçu comme unité | Fond bruité réduisant le contraste des libellés |

Application directe : « sujets côte à côte » exige que **la proximité et l'enclosure l'emportent sur les arêtes** pour grouper ; les arêtes inter-sujets sont rares et visibles comme telles.

### 2.4 Cartes conceptuelles et mind maps (Novak)

- Carte conceptuelle : propositions explicites, hiérarchie, liens croisés = intégration de connaissances (apprentissage significatif). Mind map (Buzan) : arborescence radiale à mots-clés, sans verbes de liaison ; rapide à produire mais **ambiguë** sur la nature des relations.
- Les preuves empiriques favorisent surtout la **construction active** de la carte (générative) plus que la lecture d'une carte fournie. confmap génère la carte automatiquement : le bénéfice génératif est donc **faible** sauf si l'utilisateur peut intervenir (éditer, regrouper, annoter). Critère : la carte est-elle un *organiseur à lire* (acceptable) ou prétend-elle être un outil de construction active (alors il faut de l'interaction) ?
- Une carte utile à la révision doit tenir **seule** : lisible sans la transcription.

### 2.5 Lisibilité des graphes

Esthétiques de graphes qui ont des preuves de performance (Purchase 1997 ; Ware et al. 2002) : **minimiser les croisements d'arêtes** (effet le plus fort), minimiser les coudes, éviter les arêtes qui passent sous un nœud, bonne répartition, symétrie. Aussi : angles de croisement proches de 90° quand le croisement est inévitable.

- **Densité** : au-delà d'environ 7-10 nœuds par sujet visibles simultanément, la lecture en un coup d'œil s'effondre ; préférer **replier/agréger** (sujets anciens condensés) plutôt que rétrécir la police.
- **Longueur des libellés** : étiquettes de 1 à 4 mots dans les nœuds ; phrases entières = transcription déguisée. Le texte tronqué sans possibilité de lire le complet est un échec ; la taille de police du nœud ne doit pas varier selon la longueur.
- **Chevauchements** nœud-nœud, libellé-arête, libellé-libellé : défaut direct.
- **Lisibilité Mermaid dans Obsidian** : Mermaid ne gère pas bien les graphes larges ; la carte exportée doit tenir en largeur de panneau (flowchart par sujet, `TD`/`LR` selon le type, sous-graphes par sujet), sans défilement horizontal.
- **Canvas** : grille alignée, dimensions de cartes cohérentes, groupes (`group`) pour les sujets, pas de superposition, arêtes courtes, couleurs peu nombreuses et sémantiquement stables.

### 2.6 Visualisation incrémentale et stabilité de la carte mentale

La carte se construit **pendant** la présentation : problème de **dynamic graph drawing**.

- **Mental map preservation** (Coleman & Parker 1996) : lorsqu'un nœud est ajouté, les positions existantes doivent changer **le moins possible**. Mesures de stabilité : déplacement moyen des nœuds entre deux images ; des travaux récents proposent des métriques de qualité dynamiques (Meidiana, Hong, Eades 2020, [S8]) et des approches qui garantissent la stabilité en ne déplaçant jamais les sommets en limitant les croisements par image (arXiv 2508.17532, [S9] ; je n'ai pu vérifier que le titre et la thèse, pas les auteurs).
- **Nuance empirique** : les études utilisateurs sont **mitigées** : préserver la carte mentale n'améliore pas toujours le temps ou l'erreur, mais est perçu comme utile pour la mémorisation (Archambault & Purchase, [S7]). Donc : **stabilité = bonne par défaut**, **jamais au prix de croisements ou chevauchements flagrants**. Une réorganisation globale occasionnelle est tolérable si elle est **annoncée**, animée progressivement et rare.
- *Critères confmap* : ajout d'un nœud → aucun déplacement des nœuds existants visibles au-delà d'un seuil faible ; le nouveau nœud est signalé (pré-attentif, durée brève) puis se fond ; un nouveau sujet s'ajoute **à côté** (nouvel espace) et ne repousse pas les précédents ; zéro clignotement ; zoom/défilement non modifiés par l'arrivée de contenu (pas de recentrage automatique agressif).
- **Qualité finale vs stabilité** : la carte exportée (note, canvas) peut être **re-disposée** une fois, hors direct : il est légitime que l'export soit mieux ordonné que l'écran en direct, mais le juge note si l'export contredit le modèle mental construit pendant la session (sujets dans un ordre différent sans raison).

### 2.7 Pré-attentif

Traitement en moins de 200-250 ms, sans effort : teinte, orientation, taille, mouvement, clignotement, enclosure. Un seul élément distinct parmi des semblables « saute aux yeux » ; plusieurs éléments distincts se **neutralisent**. Le mouvement est le canal le plus capteur : à réserver. *Critère* : au plus un élément pré-attentif à la fois (le dernier nœud, le sujet courant) ; l'état d'enregistrement ou d'erreur doit se voir **sans** lecture.

### 2.8 Couleur accessible

- Environ 8 % des hommes ont une déficience de la vision des couleurs (rouge-vert surtout) : **ne jamais coder l'information par la couleur seule** (ajouter forme, texte, icône, position).
- Palettes catégorielles limitées à 5-7 classes, validées pour daltonisme (type Okabe-Ito, ColorBrewer).
- **Contraste** : WCAG 2.x, ratio minimal 4,5:1 pour le texte normal, 3:1 pour le texte large (≥ 24 px ou 18,66 px gras) et composants d'interface ; critère 1.4.11 : 3:1 pour les contrôles et éléments graphiques utiles.
- En mode sombre : éviter noir pur + blanc pur (halo, fatigue) ; préférer fond gris très sombre et texte à 87-92 % de blanc ; couleurs saturées désaturées pour éviter la vibration.

---

## 3. IHM

### 3.1 Heuristiques de Nielsen (1994)

1. Visibilité de l'état du système. 2. Correspondance système / monde réel. 3. Contrôle et liberté de l'utilisateur. 4. Cohérence et standards. 5. Prévention des erreurs. 6. Reconnaître plutôt que se rappeler. 7. Flexibilité et efficacité. 8. Design esthétique et minimaliste. 9. Aider à reconnaître, diagnostiquer et corriger les erreurs. 10. Aide et documentation.

Application dominante : **n° 1** (voir 3.3), **n° 3** (pause/reprise, annuler, fermer), **n° 5** (impossible de perdre une session par un clic accidentel ; confirmation de « Fin »), **n° 8** (peu d'éléments), **n° 9** (messages d'erreur actionnables en français).

### 3.2 Huit règles d'or de Shneiderman

Cohérence ; raccourcis pour utilisateurs fréquents ; retours informatifs ; dialogues conduisant à une clôture (début-milieu-fin) ; prévention d'erreurs et gestion simple ; annulation facile ; locus de contrôle interne ; réduction de la charge de mémoire à court terme (Shneiderman et al., *Designing the User Interface*, 6e éd., 2016, révision de l'ouvrage de 1986).

- *Clôture* : le flux « session → fin → finalisation → note prête » doit montrer chaque étape et un état final clair. 
- *Mémoire à court terme* : ne jamais demander à l'utilisateur de se souvenir d'un état (« est-ce que j'enregistre ? ») : l'écran le dit.

### 3.3 Visibilité de l'état et flux de session

États à rendre **lisibles en un coup d'œil** : enregistrement en cours / en pause ; micro actif (niveau) ; connexion iPhone ; transcription à jour vs en retard (**latence Whisper**) ; traduction en attente ; carte en cours de mise à jour ; coût/jetons si pertinent ; finalisation (étapes, progression, reprise après échec).

- *Critère clé* : l'utilisateur peut dire « tout va bien » ou « quelque chose est cassé » en moins de 2 s, sans lire.
- **Échec silencieux** (micro coupé, API en erreur, quota, Wi-Fi perdu) = défaut majeur : la salle n'offre pas de seconde chance.
- **Flux de fin de session** : après « Fin », la finalisation (résumé, carte Mermaid, canvas, traduction complète) prend du temps ; l'application doit : indiquer la progression, **permettre de fermer l'ordinateur sans perte** (reprise), annoncer l'emplacement exact du fichier, et offrir « ouvrir dans Obsidian » **sans forcer le premier plan** (contrainte de l'utilisateur). Une re-traduction ou re-finalisation doit être **idempotente** et ne pas bloquer.

### 3.4 Interfaces « glanceables » et tâche secondaire

Une tâche secondaire doit être **lisible en 1-2 s** (cf. recherche auto/montre connectée ; principe d'affichage périphérique, « calm technology » de Weiser & Brown). Règles :

- **Grande taille** pour l'élément courant, **hiérarchie de taille** claire (courant ≫ récent ≫ ancien).
- **Un point focal** à la fois ; pas de lecture nécessaire pour savoir si l'essentiel a changé.
- **Pas d'interaction obligatoire** pendant la conférence : tout ce qui est interactif est **optionnel** et rapide (une note : un champ, Entrée) ; aucune fenêtre modale surgissant en cours de session.
- **Pas de vol de focus** : l'application ne prend jamais le clavier ni le premier plan sans action de l'utilisateur ; l'iPhone envoie sans que le Mac ne bascule d'application.
- **Densité d'information adaptée à la posture** : MacBook posé de côté, angle de vue oblique, éclairage de salle variable, distance 50-70 cm.

### 3.5 Mode sombre en salle

Salles souvent semi-obscures, projecteur lumineux : un écran blanc éblouit les voisins et fatigue. Mode sombre par défaut ou automatique ; **luminosité basse mais contraste suffisant** (WCAG s'applique aussi en sombre) ; éviter les grandes surfaces claires (photos de slides à fond blanc : les atténuer ou les cadrer pour ne pas créer un flash lumineux) ; **aucun son** non demandé (cloche, bip). Le thème de l'export Obsidian suit celui de la vault (pas de couleurs en dur illisibles en clair ou en sombre).

### 3.6 Accessibilité WCAG 2.2 (W3C 2023)

Critères testables : 1.4.3 contraste texte (4,5:1) ; 1.4.11 contraste non textuel (3:1) ; 1.4.4 redimensionnement du texte jusqu'à 200 % sans perte ; 1.4.1 pas de couleur seule ; 2.1.1 clavier ; 2.4.7 focus visible ; 2.5.8 taille de cible minimale 24×24 px CSS ; 4.1.3 messages d'état annoncés. Tailles typographiques indicatives pour l'usage en tâche secondaire : texte courant en direct **≥ 18-20 px** ; libellés de nœuds **≥ 14 px** effectifs ; contrôles **≥ 32 px** (idéalement 44 px).

### 3.7 Loi de Fitts

Temps de pointage ≈ a + b·log₂(D/W + 1) : cibles **grandes** et **proches**, bords/coins d'écran « infiniment profonds » sur macOS. Appliqué à confmap : boutons Pause/Fin gros, **séparés** pour éviter l'erreur (Fin ≠ Pause adjacents), actions fréquentes (note) à portée du clavier (raccourci) plutôt que de la souris ; zone de saisie de note toujours la même place.

### 3.8 Travaux récents sur les outils de prise de notes et de synthèse par LLM

- **NoTeeline** : voir 1.4 ; leçon : notes **ancrées sur l'intention** de l'utilisateur.
- **MeetMap** (2025, arXiv 2502.01564) : cartographie de dialogue en temps réel par LLM en réunion en ligne, trois modes, étude utilisateur sur la charge ; confirme l'intérêt d'une carte construite en direct mais souligne le besoin de contrôle utilisateur sur la structure [S11] (le détail des conclusions n'a pas été revérifié intégralement ; juger par la grille plutôt que par ce papier).
- **Risques LLM** : hallucination, attribution erronée, perte de nuance, sur-confiance ; pour un doctorant, une citation ou un chiffre inventé dans la note est un défaut grave. Critère : les éléments factuels de la note sont **traçables** vers la transcription (horodatage ou segment) et les incertitudes visibles.

---

## 4. Grille d'évaluation (0-3)

**Échelle** : 0 = échec observable ; 1 = présent mais gênant ; 2 = correct avec défauts mineurs ; 3 = exemplaire. Scorer chaque critère **avec une observation concrète** (capture, extrait de note, séquence de manipulations), pas sur impression. Surface : **L** = UI en direct, **N** = note Obsidian, **C** = canvas.

| # | Critère | Principe d'origine | Question concrète sur confmap | Échec observable | Surf. |
|---|---|---|---|---|---|
| 1 | Glanceabilité de l'état | Nielsen 1 ; Weiser & Brown | En 2 s sans lire, sait-on si l'enregistrement est actif, en pause ou en erreur ? | L'état exige de lire un petit texte ou n'est visible qu'au survol | L |
| 2 | Échec non silencieux | Nielsen 1 et 9 | Micro coupé, API en erreur, perte iPhone ou réseau : un signal clair et actionnable apparaît-il ? | Transcription qui s'arrête sans aucun indicateur | L |
| 3 | Latence perçue et fraîcheur | Contiguïté temporelle (Mayer) ; effet transitoire | Le texte original apparaît-il et la traduction suit-elle assez vite pour être pertinente ? Le retard est-il affiché ? | Traduction en retard de plusieurs phrases sans indication | L |
| 4 | Stabilité du texte lu | Charge extrinsèque ; effet transitoire | Une ligne en cours de lecture se déplace-t-elle ou se réécrit-elle sous les yeux ? | Défilement brutal, réécriture de segment déjà lu, saut de scroll | L |
| 5 | Alignement bilingue | Split-attention ; contiguïté spatiale | Chaque segment original est-il en face de sa traduction à la même hauteur ? | Désalignement qui s'accumule ; colonnes de longueurs divergentes | L, N |
| 6 | Justification de la redondance | Redondance ; inversion d'expertise (Kalyuga) | Peut-on masquer une colonne ? Chaque surface (transcription, carte, notes) apporte-t-elle un plus distinct ? | Mêmes phrases répétées dans la transcription et la carte sans structure ajoutée | L, N |
| 7 | Hiérarchie de taille et de focus | Glanceabilité ; pré-attentif | L'élément courant est-il nettement plus visible que l'ancien ? | Tout au même poids ; ancien et courant indiscernables | L |
| 8 | Un seul signal pré-attentif | Pré-attentif ; attention divisée | À un instant, un seul élément attire-t-il l'œil, et pour une bonne raison ? | Clignotements multiples, animations décoratives, badges concurrents | L |
| 9 | Stabilité de la carte à l'ajout | Mental map preservation (Coleman & Parker ; Archambault & Purchase) | Un nouveau nœud déplace-t-il les nœuds existants ? Le recadrage change-t-il ? | Réorganisation globale à chaque ajout ; zoom réinitialisé | L |
| 10 | Signalement du nouveau | Signalement (Mayer) ; pré-attentif | Le nouveau nœud est-il repérable brièvement puis se fond-il ? | Aucune distinction, ou surbrillance qui reste indéfiniment | L |
| 11 | Sujets côte à côte et séparation | Gestalt : proximité, enclosure | Les sujets sont-ils groupés par proximité/cadre, avec un espace inter-sujets > intra-sujet ? | Sujets entremêlés ; nœuds d'un sujet plus loin d'eux que d'un autre sujet | L, C, N |
| 12 | Type de sujet encodé fidèlement | Munzner (marques/canaux) ; organiseurs/schémas | Processus, chronologie, concept, comparaison sont-ils distingués visuellement, et correctement choisis ? | Chronologie sans ordre spatial ; comparaison sans structure parallèle ; mauvais type | L, C, N |
| 13 | Croisements et chevauchements | Purchase 1997 ; Ware 2002 | Compter les croisements d'arêtes et les chevauchements nœud/libellé | Croisements évitables ; libellés qui se recouvrent ; arêtes sous des nœuds | L, C, N |
| 14 | Densité et libellés | Charge intrinsèque ; lisibilité de graphes | Nombre de nœuds visibles par sujet ; longueur des libellés ; texte tronqué ? | Phrases entières dans les nœuds ; plus de ~10 nœuds par sujet visibles sans repli ; troncature irrécupérable | L, C, N |
| 15 | Relations nommées | Novak (propositions) | Les arêtes importantes portent-elles un verbe/relation, ou la carte est-elle un nuage de mots-clés ? | Arêtes sans sens ; impossible de dire pourquoi deux idées sont liées | L, C, N |
| 16 | Data-ink / cohérence | Tufte ; Mayer cohérence | Les éléments sans valeur d'information sont-ils absents (bordures, ombres, icônes décoratives, panneaux vides) ? | Décor, doublons d'information, éléments d'interface toujours affichés mais inutiles | L, C |
| 17 | Contraste et tailles | WCAG 1.4.3 ; 1.4.11 ; 1.4.4 | Mesurer le contraste texte/fond (≥ 4,5:1), tailles (≥ 18 px courant, ≥ 14 px nœud) | Texte gris sur gris ; libellés de nœuds minuscules ; contrôles < 24 px | L, C |
| 18 | Couleur non porteuse seule | WCAG 1.4.1 ; daltonisme | L'information passe-t-elle aussi par forme/texte/position ? Palette testée en simulation daltonisme | Types de sujet distingués seulement par teinte rouge/vert | L, C |
| 19 | Mode sombre en salle | Ergonomie salle ; WCAG | Thème sombre par défaut/auto ; pas de grande surface blanche ; photos de slides adoucies ? | Flash blanc à l'arrivée d'une photo ; thème clair éblouissant | L |
| 20 | Prise de notes sans friction | Effet de génération ; Mueller & Oppenheimer / Urry ; Fitts | Combien d'actions et de secondes pour saisir une note courte ou photographier un slide ? Le focus clavier est-il respecté ? | Plus de 2 interactions ; focus volé ; saisie qui perturbe la transcription | L |
| 21 | Aucune interruption en cours de session | Shneiderman ; attention divisée | Y a-t-il des modales, sons, notifications ou prises de premier plan non demandés ? | Fenêtre/popup au milieu d'une phrase de l'orateur ; ouverture d'une appli au premier plan | L |
| 22 | Contrôle et réversibilité | Nielsen 3 et 5 ; Shneiderman | Pause/reprise ; « Fin » protégé contre l'erreur et distant de Pause (Fitts) ; redémarrage sans perte ? | Un clic accidentel clôt la session ; reprise impossible | L |
| 23 | Flux de fin de session | Shneiderman (clôture) ; Nielsen 1 | Après « Fin » : étapes, progression, reprise après échec, chemin du fichier, délai annoncé ? | Écran figé sans progression ; blocage sur re-traduction ; fichier introuvable | L, N |
| 24 | Note : tête de révision | Récupération ; organiseur a posteriori | Résumé court, points à retenir et métadonnées (orateur, date, sujets) en tête ? | Note qui commence par la transcription ; pas de résumé | N |
| 25 | Note : hiérarchie et repli | Segmentation ; charge extrinsèque | Transcription longue repliée ? Sections nettes (résumé / carte / notes et slides / transcription) ? | Mur de texte de plusieurs pages sans repli ni titres | N |
| 26 | Note : double codage lié | Paivio ; contiguïté spatiale | Les slides apparaissent-ils à côté des notes et segments qu'ils illustrent, avec légende ? | Photos regroupées en fin de note sans lien ; carte séparée des notes | N, C |
| 27 | Note : provenance et traçabilité | Hallucination LLM ; NoTeeline (intention) | Distingue-t-on notes tapées, texte généré, transcription ? Les faits sont-ils reliés au segment source ? | Contenu généré non marqué ; chiffre ou nom sans source dans la transcription | N |
| 28 | Note et canvas : lisibilité Obsidian | Lisibilité de graphes ; Gestalt | Mermaid s'affiche-t-il sans défilement horizontal et sans débordement ? Canvas en grille, groupes, sans superposition ? | Mermaid illisible ou cassé ; cartes du canvas superposées ; arêtes parasites | N, C |
| 29 | Cohérence entre direct et export | Mental map ; schémas | La carte exportée reflète-t-elle ce que l'utilisateur a vu (mêmes sujets, mêmes regroupements) ? | Sujets réordonnés ou fusionnés sans raison ; nœuds perdus | N, C |
| 30 | Qualité des termes techniques | Charge de traduction ; hallucination | Noms propres, acronymes et termes de métier sont-ils préservés/glosés de façon cohérente ? | Même terme traduit de trois façons ; nom d'orateur déformé ; acronyme traduit | L, N |

**Usage** : (1) pour chaque critère, décrire l'observation en une ligne ; (2) scorer ; (3) lister les **trois pires scores avec correctif minimal** ; (4) comparer au tour précédent (régression = score en baisse). Les critères 1, 2, 4, 9, 21, 22 sont **bloquants** : un score de 0 invalide l'itération quelle que soit la moyenne.

---

## 5. Sources

Vérifiées par consultation en ligne lors de la rédaction ([V]) ou références canoniques de la littérature, citées de mémoire sans consultation du texte ([C]) ; le juge ne doit pas leur attribuer de résultats chiffrés au-delà de ce qui est écrit ici.

**Récentes (2018-2026)**

- [S6] [V] Huq, F., Samee, A., Lin, D. C., Tang, X. A., Bigham, J. P. (2025). *NoTeeline: Supporting Real-Time, Personalized Notetaking with LLM-Enhanced Micronotes*. IUI 2025 (accepté), arXiv:2409.16493. https://arxiv.org/abs/2409.16493
- [S8] [V] Meidiana, A., Hong, S.-H., Eades, P. (2020). *New Quality Metrics for Dynamic Graph Drawing*. GD 2020, arXiv:2008.07764. https://arxiv.org/abs/2008.07764
- [S9] [V partiel] arXiv:2508.17532 (2025), dessin de graphes dynamiques sans déplacer les sommets ni créer de croisements par image ; auteurs et titre exact non vérifiés, à citer par son identifiant uniquement. https://arxiv.org/abs/2508.17532
- [S10] [V] Urry, H. L., et al. (2021). *Don't Ditch the Laptop Just Yet: A Direct Replication of Mueller and Oppenheimer's (2014) Study 1 and Mini Meta-Analysis*. Psychological Science, DOI 10.1177/0956797620965541. https://journals.sagepub.com/doi/10.1177/0956797620965541
- [S11] [V partiel] MeetMap: Real-Time Collaborative Dialogue Mapping with LLMs in Online Meetings (2025), arXiv:2502.01564 ; auteurs non revérifiés. https://arxiv.org/abs/2502.01564
- [S12] [V partiel] Équipe de l'Université d'Anvers, sous-titres intralinguistiques en direct en cours dispensés en anglais (projet depuis 2021) ; article pilote dans *Translation Spaces*, DOI 10.1075/ts.25017.van ; auteurs non vérifiés (page protégée). https://www.jbe-platform.com/content/journals/10.1075/ts.25017.van
- [S13] [V] Sweller, J., Ayres, P., Kalyuga, S., Chandler, P. (2003). *The expertise reversal effect*. Educational Psychologist 38(1) (nommé dans la page de dépôt de l'Université de Wollongong). https://ro.uow.edu.au/edupapers/136
- [S14] [V partiel] Étude trans-kom (EMI, sous-titrage en direct, 2026) citée par le moteur de recherche : <https://www.trans-kom.eu/bd19nr01/trans-kom_19_01_15_Gauwbergen_ua_EMI.20260615.pdf> ; cadre « texte visuel + parole = surcharge possible ». Utiliser comme contexte, pas comme preuve.

**Classiques (références canoniques [C])**

- [S1] Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science* 12(2).
- [S2] Sweller, J., Ayres, P., Kalyuga, S. (2011). *Cognitive Load Theory*. Springer.
- [S3] Mayer, R. E. (2009, 2e éd. ; 3e éd. 2021). *Multimedia Learning*. Cambridge University Press.
- [S4] Paivio, A. (1986). *Mental Representations: A Dual Coding Approach*. Oxford University Press.
- [S5] Ausubel, D. P. (1960). The use of advance organizers in the learning and retention of meaningful verbal material. *Journal of Educational Psychology* 51(5).
- [S7] Archambault, D., Purchase, H. C. : travaux sur « The Map in the Mental Map » (expériences en dessin de graphes dynamiques, IJHCS, 2013) et « The mental map and memorability in dynamic graphs » (PacificVis 2012) ; titres retrouvés par recherche, détails non revérifiés.
- [S15] Mueller, P. A., Oppenheimer, D. M. (2014). The pen is mightier than the keyboard. *Psychological Science* 25(6).
- [S16] Roediger, H. L., Karpicke, J. D. (2006). Test-enhanced learning. *Psychological Science* 17(3).
- [S17] Cepeda, N. J., et al. (2006). Distributed practice in verbal recall tasks. *Psychological Bulletin* 132(3).
- [S18] Dunlosky, J., et al. (2013). Improving students' learning with effective learning techniques. *Psychological Science in the Public Interest* 14(1).
- [S19] Novak, J. D., Cañas, A. J. (2008). *The Theory Underlying Concept Maps and How to Construct and Use Them*. Technical Report IHMC CmapTools 2006-01 Rev 01-2008.
- [S20] Tufte, E. R. (1983). *The Visual Display of Quantitative Information*. Graphics Press.
- [S21] Munzner, T. (2014). *Visualization Analysis and Design*. CRC Press.
- [S22] Purchase, H. C. (1997). Which aesthetic has the greatest effect on human understanding? *Graph Drawing 1997*. Ware, C., et al. (2002). Cognitive measurements of graph aesthetics. *Information Visualization* 1(2).
- [S23] Coleman, M. K., Parker, D. S. (1996). Aesthetics-based graph layout for human consumption. *Software: Practice and Experience* 26(12).
- [S24] Nielsen, J. (1994). Enhancing the explanatory power of usability heuristics. *CHI '94* ; Nielsen, J. 10 Usability Heuristics. https://www.nngroup.com/articles/ten-usability-heuristics/
- [S25] Shneiderman, B., Plaisant, C., Cohen, M., Jacobs, S., Elmqvist, N. (2016). *Designing the User Interface*, 6e éd. Pearson.
- [S26] Fitts, P. M. (1954). The information capacity of the human motor system in controlling the amplitude of movement. *Journal of Experimental Psychology* 47(6).
- [S27] W3C (2023). *Web Content Accessibility Guidelines (WCAG) 2.2*. https://www.w3.org/TR/WCAG22/
- [S28] Weiser, M., Brown, J. S. (1996). Designing calm technology. *PowerGrid Journal* 1.01.
- [S29] Mayer, R. E., Fiorella, L. (2014). Principles for reducing extraneous processing in multimedia learning, dans *The Cambridge Handbook of Multimedia Learning*, 2e éd. (redondance : 16 comparaisons sur 16 en faveur de l'absence de texte redondant d'après une source secondaire non revérifiée).
- [S30] Kalyuga, S. (2007). Expertise reversal effect and its implications for learner-tailored instruction. *Educational Psychology Review* 19.

Total : **30 références** (8 vérifiées ou partiellement vérifiées en ligne, dont 7 de 2018-2026 ; le reste sont des classiques cités de mémoire).
