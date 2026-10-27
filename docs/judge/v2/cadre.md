# Cadre du juge v2 — apprentissage, visualisation, IHM

Cadre réécrit de zéro (octobre 2026). Le juge le lit **en entier avant de toucher à l'application**.
Chaque principe se termine par **→ À vérifier**, une observation concrète sur confmap. Grille en §5.

## 0. Persona et scénarios

**Persona** : doctorante ou doctorant en salle, MacBook sur les genoux, conférence en anglais (langue non maternelle).
Le regard est sur l'orateur et les slides projetés ; l'écran ne reçoit que des **coups d'œil de 1 à 3 s**.
Trois jours plus tard, la même personne **révise** dans Obsidian, sans souvenir précis de l'exposé.

Le juge déroule et note quatre scénarios, chacun relié à une surface :

| Scénario | Surface | Question de succès |
|---|---|---|
| S1 Coup d'œil | UI direct | En 2 s : ça enregistre ? de quoi parle-t-on maintenant ? qu'est-ce qui vient d'être dit ? |
| S2 Rattrapage | UI direct | Après 30 s d'inattention, retrouver le fil (où en est l'orateur, ce que j'ai manqué) en < 10 s |
| S3 Capture | UI direct + iPhone | Noter une idée ou photographier un slide sans perdre le fil, ≤ 2 actions |
| S4 Révision | Note Obsidian + canvas | En 2 min, reconstituer la structure de l'exposé et retrouver une affirmation précise avec sa source |

---

## 1. Théorie de l'apprentissage

**1.1 Charge cognitive (Sweller 1988 ; Sweller, Ayres, Kalyuga 2011).** Mémoire de travail limitée.
Charge intrinsèque (complexité du contenu), extrinsèque (imposée par la présentation, à minimiser),
germane (construction de schémas, à favoriser). Écouter en L2 + lire + noter = charge déjà maximale.
→ À vérifier : chaque élément affiché aide-t-il à comprendre ? Lister ce qui pourrait disparaître sans perte.

**1.2 Apprentissage multimédia (Mayer 2021).** Principes retenus :
cohérence (retirer le superflu), signalement (mettre en relief l'essentiel), redondance (texte identique
à la parole = surcharge, sauf L2 où les sous-titres aident), contiguïté spatiale et temporelle (ce qui va
ensemble est montré ensemble, au même moment), segmentation (unités digestes), pré-entraînement
(termes clés donnés avant).
→ À vérifier : traduction en face de l'original, carte synchronisée avec la parole, glossaire des termes clés visible tôt.

**1.3 Double codage (Paivio 1986).** Verbal + visuel liés = meilleure rétention, à condition que le lien soit explicite.
→ À vérifier : un nœud de carte renvoie-t-il au passage de transcription, et un slide aux idées qu'il illustre ?

**1.4 Organiseurs avancés et schémas (Ausubel 1960).** Une structure d'ensemble donnée avant/pendant
facilite l'ancrage des détails. → À vérifier : plan des sujets visible en direct ; résumé et carte en tête de note.

**1.5 Effet de génération et prise de notes (Slamecka & Graf 1978 ; Mueller & Oppenheimer 2014 ; Urry et al. 2021).**
Reformuler soi-même aide à retenir ; la copie verbatim aide peu. L'outil doit laisser la place à la note
personnelle et ne pas la noyer dans le texte généré. → À vérifier : notes personnelles distinctes et mises en valeur dans la note finale.

**1.6 Récupération et espacement (Roediger & Karpicke 2006 ; Dunlosky et al. 2013).** Se tester vaut mieux que relire.
→ À vérifier : la note propose-t-elle des questions de rappel, des points à retenir, quelque chose à faire en révision ?

**1.7 Effet transitoire et attention divisée.** L'information qui défile disparaît ; en double tâche,
l'œil doit retrouver instantanément sa place. → À vérifier : rien ne bouge sous le regard ; un repère stable du « maintenant ».

**1.8 Inversion d'expertise (Kalyuga 2007).** Ce qui aide le novice gêne l'expert.
→ À vérifier : peut-on masquer une colonne, réduire la carte, régler la densité ?

## 2. Visualisation

**2.1 Tufte (1983) : encre-données, chartjunk, micro/macro.** Toute encre doit porter de l'information ;
une bonne vue sert à la fois la vue d'ensemble et le détail. → À vérifier : décor (dégradés, halos,
grille de points, ombres) qui n'encode rien ; vue d'ensemble + détail sur une même carte.

**2.2 Munzner (2014) : what / why / how ; efficacité des canaux.** Position > longueur > angle > surface > couleur (quantitatif) ;
teinte et forme pour le catégoriel ; ne pas encoder plus de catégories que l'œil n'en distingue (~6-8 teintes).
→ À vérifier : le type de sujet (processus, chronologie, concept, comparaison) est-il encodé par la disposition
(position) et non par la seule couleur ?

**2.3 Mantra de Shneiderman (1996).** Vue d'ensemble d'abord, zoom et filtre, détails à la demande.
→ À vérifier : vue d'ensemble disponible en 1 action ; détail (source d'un nœud) à la demande.

**2.4 Gestalt.** Proximité, similarité, enclosure (région commune), continuité, connexion.
→ À vérifier : espace inter-sujets nettement > intra-sujet ; un cadre par sujet ; similarité de style = même rôle.

**2.5 Cartes conceptuelles (Novak & Cañas 2008).** Une carte = propositions (concept – relation nommée – concept),
hiérarchie, liens transversaux. Un nuage de mots-clés n'est pas une carte. → À vérifier : arêtes étiquetées par un verbe ; lecture d'une proposition possible.

**2.6 Lisibilité des graphes (Purchase 1997 ; Ware et al. 2002).** Croisements d'arêtes = premier facteur d'erreur ;
puis coudes, symétrie, longueur des arêtes. → À vérifier : compter croisements et chevauchements.

**2.7 Carte mentale dynamique (Misue et al. 1995 ; Archambault & Purchase 2013).** En dessin incrémental, préserver
positions, orthogonalité et proximité des nœuds existants ; animer la transition.
→ À vérifier : entre deux captures successives, des nœuds anciens ont-ils bougé ?

**2.8 Attributs pré-attentifs (Treisman ; Healey & Enns 2012).** Couleur, mouvement, taille, orientation sont
détectés en < 250 ms ; un seul signal à la fois sinon il n'y a plus de signal. → À vérifier : combien d'éléments attirent l'œil simultanément ?

**2.9 Couleur (Brewer ; Okabe-Ito ; WCAG 1.4.1).** Palettes distinguables par daltoniens ; la couleur ne porte jamais seule l'information.

**2.10 Typographie à l'écran.** Corps ≥ 16-18 px en lecture courante à distance de bras ; 45-75 caractères/ligne ;
interlignage 1,4-1,6 ; contraste texte/fond ≥ 4,5:1 (7:1 idéal en salle sombre).

## 3. IHM

**3.1 Norman (2013) — action et perception.** Affordances et signifiants (le bouton dit ce qu'il fait), retour immédiat
de chaque action, modèle conceptuel cohérent, contraintes qui empêchent l'erreur, **gouffre d'exécution**
(comment je fais X ?) et **gouffre d'évaluation** (est-ce que ça a marché ?).
→ À vérifier : pour chaque bouton (⚡, ⤢, ↻, 📄, 📱, ■), deviner sa fonction sans infobulle, puis vérifier le retour.

**3.2 Heuristiques de Nielsen (1994).** Visibilité de l'état ; correspondance avec le monde réel ; contrôle et liberté ;
cohérence et standards ; prévention des erreurs ; reconnaissance plutôt que rappel ; flexibilité ; esthétique minimaliste ;
aide à diagnostiquer et réparer les erreurs ; aide et documentation.

**3.3 Critères ergonomiques de Bastien & Scapin (1993).** Guidage (incitation, groupement, feedback, lisibilité) ;
charge de travail (brièveté, densité informationnelle) ; contrôle explicite ; adaptabilité ; gestion des erreurs ;
homogénéité ; signifiance des codes et dénominations ; compatibilité. Grille de référence de l'ergonomie francophone.

**3.4 Règles d'or de Shneiderman (2016).** Cohérence, raccourcis pour habitués, retour informatif, dialogues qui se
terminent (clôture), prévention des erreurs, annulation facile, contrôle à l'utilisateur, faible charge mémoire.

**3.5 ISO 9241-110 (2020) et 9241-11 (2018).** Adéquation à la tâche, auto-descriptivité, conformité aux attentes,
apprenabilité, contrôlabilité, robustesse aux erreurs, engagement. Utilisabilité = efficacité, efficience, satisfaction **dans un contexte d'usage donné** (ici : la salle).

**3.6 Lois quantitatives.** Fitts (1954) : cible petite et lointaine = lente et fautive ; actions destructives loin
des fréquentes. Hick-Hyman : temps de choix ∝ log du nombre d'options. Miller (1956) / Cowan (2001) : ~4 éléments en mémoire de travail.

**3.7 Divulgation progressive (Nielsen 2006).** Montrer d'abord l'essentiel, le reste à la demande.
→ À vérifier : nombre de contrôles visibles en permanence pendant le direct.

**3.8 Interruption et reprise de tâche (McFarlane & Latorella 2002 ; Altmann & Trafton 2002).** Après une interruption,
il faut un **repère de reprise** (« où en étais-je »). → À vérifier : scénario S2.

**3.9 Technologie calme et interfaces « glanceables » (Weiser & Brown 1996 ; Matthews et al. 2006).**
L'information vit en périphérie et ne passe au centre que si nécessaire. → À vérifier : aucune animation, son ou fenêtre non sollicités.

**3.10 Interaction humain-IA (Amershi et al. 2019, 18 lignes directrices).** Dire ce que le système sait faire et à quel
niveau de qualité ; montrer les sorties contextuellement ; **faciliter la correction et le rejet** ; expliquer pourquoi
le système a fait ce qu'il a fait ; signaler l'incertitude ; apprendre des corrections.
→ À vérifier : peut-on corriger un nœud ou un terme mal transcrit ? Le contenu généré est-il distingué du verbatim ?

**3.11 Esthétique et utilisabilité (Tractinsky et al. 2000).** Le beau est perçu comme plus utilisable, ce qui peut
masquer des défauts. Le juge évalue la lisibilité réelle, pas l'impression. → À vérifier : le thème (translucidité,
dégradés, grille de points) dégrade-t-il le contraste ou la lisibilité ?

**3.12 Accessibilité (WCAG 2.2, W3C 2023).** Contraste 1.4.3 / 1.4.11, redimensionnement 1.4.4, focus visible 2.4.7,
taille de cible 2.5.8 (≥ 24 px), pas d'info par la couleur seule 1.4.1, mouvement réductible 2.3.3 (`prefers-reduced-motion`).

---

## 4. Règles du juge

- Juger **sur observation** (capture, extrait de note, mesure). Distinguer « observé » de « supposé ».
- Mesurer quand c'est possible : contraste (calcul à partir des couleurs CSS), tailles de police, nombre de croisements,
  déplacement de nœuds entre deux captures, nombre de clics.
- Ne citer aucun résultat chiffré d'étude qui ne figure pas ici.
- Thème sombre seul : volontaire (salle). Ne pas pénaliser l'absence de thème clair.

## 5. Grille (0 à 3 par critère, 24 critères, max 72)

0 = échec observable ; 1 = présent mais gênant ; 2 = correct, défauts mineurs ; 3 = exemplaire.
**Bloquants** (un 0 invalide l'itération) : A1, A4, B1, C1.

### A. UI en direct — coup d'œil et rattrapage (S1, S2)
| # | Critère | Principes |
|---|---|---|
| A1 | État d'enregistrement lisible en 2 s, erreurs signalées et actionnables | Nielsen 1, 9 ; Norman (évaluation) |
| A2 | « Maintenant » repérable : sujet courant + dernier passage nettement distingués | Signalement ; pré-attentif ; reprise de tâche |
| A3 | Rattrapage après 30 s : repère de reprise, ce qui a été manqué | McFarlane ; Altmann & Trafton |
| A4 | Stabilité : rien ne bouge ni ne se réécrit sous le regard ; carte sans déplacement des anciens nœuds | Effet transitoire ; carte mentale dynamique |
| A5 | Contiguïté bilingue : original et traduction alignés, latence acceptable ou affichée | Mayer contiguïté ; redondance L2 |
| A6 | Lisibilité typographique et contraste (mesurés) | WCAG ; typographie |
| A7 | Un seul signal pré-attentif ; décor sans valeur absent | Pré-attentif ; Tufte ; Mayer cohérence ; Tractinsky |

### B. UI en direct — contrôle et capture (S3)
| # | Critère | Principes |
|---|---|---|
| B1 | Aucune interruption non sollicitée (modale, son, premier plan, flash blanc) | Technologie calme ; Shneiderman |
| B2 | Signifiants : chaque contrôle compréhensible sans infobulle ; dénominations claires | Norman ; Bastien & Scapin (signifiance) |
| B3 | Divulgation progressive : peu de contrôles permanents, le reste à la demande | Hick-Hyman ; Nielsen 8 |
| B4 | Capture de note / slide en ≤ 2 actions, focus respecté, retour visible | Génération ; Fitts ; Norman (retour) |
| B5 | Contrôle et réversibilité : pause, fin protégée et éloignée, reprise sans perte | Nielsen 3, 5 ; Fitts |
| B6 | Correction et rejet du contenu IA (nœud, terme) ; incertitude signalée | Amershi et al. |
| B7 | Fin de session : progression, étapes, durée, chemin du fichier, reprise après échec | Shneiderman (clôture) |

### C. Carte des idées (direct et export)
| # | Critère | Principes |
|---|---|---|
| C1 | Carte lisible : pas de chevauchement, croisements minimaux | Purchase ; Ware |
| C2 | Sujets séparés par proximité et enclosure | Gestalt |
| C3 | Type de sujet encodé par la disposition, choix du type pertinent | Munzner ; organiseurs |
| C4 | Propositions : relations nommées, libellés courts, ≤ ~8 nœuds par sujet | Novak ; charge intrinsèque |
| C5 | Vue d'ensemble + détails à la demande (source d'un nœud) | Mantra de Shneiderman ; double codage |
| C6 | Cohérence direct ↔ export (mêmes sujets, mêmes regroupements) | Carte mentale ; schémas |

### D. Note Obsidian et canvas (S4)
| # | Critère | Principes |
|---|---|---|
| D1 | Tête de révision : résumé, points clés, métadonnées, structure annoncée | Ausubel ; organiseur |
| D2 | Hiérarchie et repli : sections nettes, transcription repliée, pas de mur de texte | Segmentation ; Mayer |
| D3 | Rappel actif : questions, points à retenir, éléments à réviser | Roediger & Karpicke ; Dunlosky |
| D4 | Notes personnelles et slides mis en valeur et liés au moment de l'exposé | Génération ; Paivio ; contiguïté |

**Rapport** : score par critère avec preuve ; trois pires critères avec correctif minimal ; problèmes classés
(bloquant / majeur / mineur) avec principe violé et correction concrète.

## 6. Sources

Classiques (références canoniques) : Sweller (1988), *Cognitive Science* 12(2) ; Sweller, Ayres & Kalyuga (2011), *Cognitive Load Theory*, Springer ;
Mayer (2021), *Multimedia Learning*, 3e éd., CUP ; Paivio (1986), *Mental Representations*, OUP ; Ausubel (1960), *J. Educ. Psychol.* 51(5) ;
Slamecka & Graf (1978), *J. Exp. Psychol.: HLM* 4(6) ; Mueller & Oppenheimer (2014), *Psychol. Sci.* 25(6) ; Urry et al. (2021), *Psychol. Sci.* 32(3) ;
Roediger & Karpicke (2006), *Psychol. Sci.* 17(3) ; Dunlosky et al. (2013), *PSPI* 14(1) ; Kalyuga (2007), *Educ. Psychol. Rev.* 19 ;
Tufte (1983), *The Visual Display of Quantitative Information* ; Munzner (2014), *Visualization Analysis and Design*, CRC ;
Shneiderman (1996), « The eyes have it », *IEEE VL* ; Novak & Cañas (2008), rapport IHMC ; Purchase (1997), *GD'97* ; Ware et al. (2002), *Inf. Vis.* 1(2) ;
Misue, Eades, Lai & Sugiyama (1995), *J. Vis. Lang. Comput.* 6(2) ; Archambault & Purchase (2013), *IJHCS* 71 ; Healey & Enns (2012), *IEEE TVCG* 18(7) ;
Norman (2013), *The Design of Everyday Things*, éd. révisée ; Nielsen (1994), *CHI'94* ; Bastien & Scapin (1993), rapport technique INRIA n° 156 ;
Shneiderman et al. (2016), *Designing the User Interface*, 6e éd. ; ISO 9241-110:2020 ; ISO 9241-11:2018 ; Fitts (1954), *J. Exp. Psychol.* 47(6) ;
Hick (1952), *QJEP* 4 ; Miller (1956), *Psychol. Rev.* 63(2) ; Cowan (2001), *BBS* 24 ; McFarlane & Latorella (2002), *HCI* 17(1) ;
Altmann & Trafton (2002), *Cognitive Science* 26(1) ; Weiser & Brown (1996), « Designing calm technology » ; Matthews et al. (2006), *Pervasive* ;
Amershi et al. (2019), « Guidelines for Human-AI Interaction », *CHI'19* ; Tractinsky, Katz & Ikar (2000), *Interacting with Computers* 13(2) ; W3C (2023), WCAG 2.2.
