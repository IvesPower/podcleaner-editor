# PodCleaner-editor : montage podcast automatisé, idée de base

**Français** · [English](spec.md) — ce document est l'original et fait foi.

Nov 5, 2026 · @Julien — révisé le 21 nov. 2026 (piste stéréo des deux voix, Claude par le compte intégré, interface de la CLI), révisé le 23 nov. 2026 (marqueurs vocaux : appel à Claude et verbe d'action), révisé le 24 nov. 2026 (porte, sorties du montage), révisé le 28 nov. 2026 (consignes gardées dans l'audio, marqueurs simples)

## Contexte et objectif

L'objectif est un outil en ligne de commande qui fait le travail répétitif du montage d'un épisode, du fichier brut au fichier prêt à finaliser. Il remplace Auphonic pour le traitement du son et prépare le travail manuel restant avec des timecodes.

L'outil tourne sur macOS et Windows et est publié en open source sur GitHub. Il doit rester utilisable sans Claude : les fonctions qui passent par Claude sont un plus, pas un prérequis. Claude est joint par le compte intégré (l'abonnement Claude, via la CLI Claude Code), jamais par une clé d'API.

## Fonctionnalités

| Fonctionnalité | Ce qu'elle fait | Outils open source | Apport de Claude |
| --- | --- | --- | --- |
| Son studio | Débruitage, réduction de la réverb, EQ, compression, de-esser sur chaque piste, puis mixage normalisé à -16 LUFS et -1 dBTP | ffmpeg, DeepFilterNet, nara\_wpe | Choisir les réglages à partir des mesures de chaque piste |
| Porte | Sur chaque piste de voix, ramène au silence numérique les passages où la personne ne parle pas, comme Strip Silence de Logic Pro (-30 dB, 0,5 s, attaque 10 ms, relâchement 0,1 s). Décidée sur le niveau sonore, avec le test de repisse, pas sur la détection de parole : les rires et les respirations restent | Niveaux de l'analyse, numpy | Aucun |
| Blancs | Raccourcit à environ 0,4 s tout silence de plus de 1 s où toutes les pistes se taisent, avec un fondu | Silero VAD par piste, ffmpeg | Aucun |
| Hésitations | Retire les « euh » isolés qui ne cassent pas la phrase, signale les autres | faster-whisper ou mlx-whisper (timestamps par mot), piste par piste | Juger, phrase par phrase, si une coupe reste naturelle |
| Paroles qui se chevauchent | Repère une personne qui tente de parler par-dessus une autre sans prendre la parole ; pose un timecode, le traitement se fait à la main. Seulement avec une piste par voix | Chevauchements détectés par VAD sur chaque piste | Écarter les relances (« oui », « mmh ») et les rires pour ne signaler que les vraies tentatives |
| Marqueurs vocaux | Repère un appel à Claude en début de phrase (« dis Claude, … » ou « Claude, … ») suivi d'une consigne qui contient un verbe d'action : couper, supprimer… pour une coupe demandée ; ajouter, extrait… pour un extrait à ajouter. La consigne reste dans l'audio, avec un marqueur : c'est au montage à la main de la couper | Whisper + règles sur les mots (rapidfuzz pour le déclencheur) | Reconnaître les variantes de formulation |
| Extraits de film | Repère chaque passage diffusé, grâce à l'activité sur la piste film | Détection d'activité sur la piste dédiée | Aucun |
| Suggestions de coupe | Propose des passages à retirer, avec la raison | Aucun | Lecture de la transcription, guidée par des exemples tirés des épisodes déjà montés |

Le mode `--dry-run` produit le rapport et les timecodes sans modifier l'audio, pour valider les réglages sur les premiers épisodes.

## Formes d'enregistrement acceptées

L'épisode arrive sous l'une de deux formes, toujours avec la piste film à part :

| Forme | Fichiers | Ce qui change |
| --- | --- | --- |
| Pistes séparées (`separate`) | Un WAV par voix (deux) + le WAV de la piste film | Tout le traitement décrit ici |
| Voix mélangées (`mixed`) | Un WAV stéréo qui contient les deux voix + le WAV de la piste film | Voir ci-dessous |

Avec les voix mélangées, on ne peut pas séparer les deux personnes :

- **Chevauchements** : ni repérés, ni coupés. Le rapport indique qu'ils ne sont pas disponibles pour cet épisode.
- **Hésitations** : un « euh » n'est retiré que si aucune autre parole ne passe en même temps (aucun autre mot transcrit dans la fenêtre de la coupe) ; sinon il est seulement signalé.
- **Son studio** : une seule chaîne de traitement, réglée pour les deux voix ensemble.
- **Blancs, marqueurs vocaux, extraits de film, suggestions** : inchangés.
- **Sorties** : la piste des voix traitée et la piste film, coupées aux mêmes endroits, plus le mixage stéréo.

La forme est donnée par le nombre de fichiers de voix passés à la commande (un ou deux), ou par la réponse à l'assistant `init`.

## Architecture

Le programme est une CLI Python qui fait tout le traitement en local. Claude s'y ajoute à deux endroits, toujours en option : la CLI Claude Code en mode non interactif (`claude -p`, avec l'abonnement de la personne) pour les décisions qui demandent du jugement, et des skills pour piloter l'outil en langage naturel.

*Schéma d'architecture : cœur local, deux couches Claude optionnelles (voir la liste ci-dessous).*

Les traits pointillés marquent ce qui est optionnel. Sans Claude Code connecté, l'étape Décisions applique seulement des règles fixes.

- **Les outils open source gardent le traitement du signal.** Claude n'écoute pas l'audio : il lit la transcription horodatée et les mesures. Le débruitage, la normalisation et les coupes restent dans ffmpeg et les modèles locaux, ce qui les rend gratuits et reproductibles.
- **Claude intervient là où une règle échoue.** Savoir si un « euh » peut sauter sans casser la phrase, reconnaître un marqueur mal transcrit, repérer un passage hors sujet : ce sont des jugements sur le sens, pas sur le signal.
- **Claude passe par le compte intégré.** Le programme lance la CLI Claude Code installée et connectée (`claude auth login`), sans outils, sans session gardée, sans réglages ni MCP, depuis un dossier temporaire, et sans `ANTHROPIC_API_KEY` dans son environnement. Si la CLI manque, n'est pas connectée ou renvoie une erreur, le programme continue avec les règles fixes et le signale.
- **Les skills enveloppent la CLI, ils ne la remplacent pas.** Un skill ne tourne que dans Claude Code. La CLI doit donc fonctionner seule, pour les contributeurs du dépôt et pour l'automatisation. Le dossier `skills/` du dépôt contient ensuite des skills qui l'appellent : montage complet, relecture du rapport, réglage d'un épisode difficile.

Points de vigilance, pour des épisodes d'environ 2 h 10 :

- **Temps de calcul.** Chaque piste fait 2 h 10. On ne transcrit que les passages où la piste est active, ce qui réduit nettement le volume. Sur un Mac Apple Silicon ou un PC avec carte NVIDIA, c'est raisonnable ; sur un processeur seul, il faut prévoir de lancer le traitement et le laisser tourner.
- **Taille envoyée à Claude.** Pour les suggestions de coupe, la transcription horodatée par phrase d'un épisode entier tient en un appel. Pour juger les « euh », on n'envoie que la phrase autour de chaque candidat, sans les timestamps par mot de tout l'épisode.
- **Consommation de l'abonnement par épisode** (nombre d'appels, temps), à mesurer sur le premier épisode test.
- **Reproductibilité** : les avis rendus par Claude sont journalisés dans le fichier de montage.

## Interface en ligne de commande

- **Nom** : `podcleaner-editor`, avec l'alias court `pedit`. Installation : `uv tool install git+https://github.com/IvesPower/podcleaner-editor`.
- **Commandes** : `init`, `run`, `config [--path]`, `version` (et `--version`). La commande seule affiche l'aide.
- **Bannière** : le nom en pixel art aux couleurs du podcast (lettres crème #fbf2f1 sur pastille rouille #94380c, comme podcleaner-clips) au début de `init`, de `run` et de la commande seule ; jamais hors terminal ; `--no-banner` ou `PODCLEANER_EDITOR_NO_BANNER=1` ; titre sur une ligne si le terminal est trop étroit ou ne sait pas afficher les blocs.
- **Assistant `init`** : pose les questions dans la console (dossier de sortie, forme d'enregistrement, prénoms des deux voix, Claude oui ou non, avec la vérification que Claude Code est connecté) et écrit le fichier de configuration commenté avec les réponses ; propose les valeurs actuelles par défaut ; remplace un fichier existant après confirmation. Hors terminal ou avec `--no-input` : le modèle commenté, sans questions.
- **Configuration** : un fichier TOML par personne, dans le dossier de configuration de l'utilisateur, remplaçable par `--config` ou `PODCLEANER_EDITOR_CONFIG` ; aucun chemin en dur.
- **Progression** : une ligne par étape pendant `run`, puis le chemin des fichiers écrits.

## Sorties produites

- **Pistes finales** : une piste traitée par personne (ou la piste des voix, si elles arrivent mélangées) et la piste film, coupées aux mêmes endroits, à l'échantillon près, avec un fondu enchaîné à chaque raccord, pour rester synchronisées et prêtes à glisser dans le logiciel de montage. Chaque piste de voix passe d'abord par la porte. Un mixage stéréo (somme des pistes, sans normalisation avant M4) est aussi produit. Fichiers : `<nom>.<voix>.wav` (un par voix), `<nom>.film.wav`, `<nom>.mix.wav`, `<nom>.markers.mid`, avec `<nom>.edit.md`. Sans `--dry-run` seulement.
- **Fichier de montage (.md)** : un seul fichier Markdown par épisode, en anglais, en deux parties.
  - Timecodes : chaque événement avec son type (coupe demandée, extrait à ajouter, extrait de film, chevauchement, suggestion), le timecode sur l'audio original et sur l'audio final, et la raison.
  - Rapport : les mesures avant et après (LUFS, true peak) par piste, le nombre de blancs et d'hésitations retirés, les « euh » signalés sans être coupés, et les avis rendus par Claude.
- **Marqueurs** : un fichier MIDI qui ne contient que les marqueurs, et les mêmes marqueurs inscrits dans le WAV du mixage. Logic Pro et Cakewalk savent lire l'un ou l'autre ; le bon format est à confirmer en test sur chaque logiciel.

Toutes les analyses se font sur l'audio original. Le programme garde la carte des coupes pour recaler chaque timecode sur le fichier final.

## Hors périmètre, décisions et questions ouvertes

La première version ne fait pas le montage créatif (choix des extraits, ordre des séquences, habillage sonore) ni la publication de l'épisode. Elle ne sépare pas non plus deux voix enregistrées ensemble.

| Sujet | Décision |
| --- | --- |
| Enregistrement | Toujours deux personnes, plus la piste film à part : une piste par personne, ou une piste stéréo qui contient les deux voix |
| Format des bruts | WAV uniquement, à la meilleure qualité d'enregistrement |
| Durée des épisodes | Environ 2 h 10 |
| Extraits de film | Diffusés en direct pendant l'enregistrement, sur une piste séparée |
| Logiciel de montage | Logic Pro |
| Référence pour le son | Plusieurs épisodes bruts avec leur version traitée par Auphonic |
| Référence pour le style | Plusieurs dizaines d'heures d'épisodes montés, avec leurs bruts sans les extraits de film |
| Chevauchements | Timecode seul, aucune baisse de volume automatique ; aucun repérage avec les voix mélangées |
| Fichier de sortie | Un seul .md par épisode : timecodes et rapport |
| Accès à Claude | Compte intégré : la CLI Claude Code connectée, avec l'abonnement ; jamais de clé d'API. La transcription peut lui être envoyée |
| Langue du programme | Anglais : messages, erreurs, aide, fichier de montage, clés de la configuration. Les marqueurs vocaux restent des phrases dites en français |
| Langue de la documentation | Anglais (`nom.md`) et français (`nom.fr.md`), mis à jour ensemble ; ce cahier des charges en français fait foi |

Les paires brut / Auphonic servent de banc d'essai : chaque version du traitement est mesurée contre elles (loudness, spectre, bruit de fond) avant d'être publiée.

Les bruts n'ont pas les extraits de film : l'alignement des transcriptions les traite comme des ajouts et ne les compte pas comme des coupes.

Aucune question ouverte à ce stade : le cadrage est complet pour démarrer.

## Outils pour développer le projet

Le projet se développe dans Claude Code avec quelques plugins généralistes, trois MCP et des skills écrits pour le projet. Mieux vaut peu d'outils bien choisis : chaque plugin chargé occupe une partie du contexte.

| Outil | Type | À quoi il sert ici | Où le trouver |
| --- | --- | --- | --- |
| Superpowers | Skills | Plans, tests écrits avant le code, débogage méthodique, module par module | obra/superpowers |
| feature-dev | Plugin | Cadre chaque fonctionnalité en phases, de l'exploration à la revue | Marketplace officiel Anthropic |
| python-development | Plugin | Agent spécialisé Python (packaging, typage, tests) | wshobson/agents |
| skill-creator | Skill | Écrire les skills propres au projet | anthropics/skills |
| Hooks Ruff et pytest | Hooks | Lint et tests lancés après chaque modification de fichier Python | `.claude/settings.json` du dépôt |
| GitHub | MCP | Issues, pull requests et CI du dépôt open source | github/github-mcp-server |
| Context7 | MCP | Documentation à jour de faster-whisper, DeepFilterNet, Silero VAD, ffmpeg | upstash/context7 |
| Hugging Face | MCP | Chercher et comparer les modèles audio et de transcription | Serveur MCP officiel Hugging Face |

Skills à écrire pour le projet, versionnés dans `.claude/skills/` :

- **Comparaison Auphonic** : traite un épisode de référence et compare la sortie à la version Auphonic (LUFS, true peak, spectre, bruit de fond).
- **Test rapide** : fait tourner toute la chaîne sur un extrait de 10 minutes des pistes voix et de la piste film, pour vérifier une modification sans traiter 2 h 10.
- **Compatibilité Windows** : vérifie les chemins, la présence de ffmpeg et l'encodage des fichiers avant chaque version.

Un fichier `CLAUDE.md` à la racine reprend les décisions de ce document et les règles du dépôt. Claude Code le relit au début de chaque session.

Sources : [Dupple, meilleurs skills Claude Code 2026](https://dupple.com/learn/best-claude-code-skills-2026) · [Redwerk, meilleurs plugins Claude Code 2026](https://redwerk.com/blog/best-claude-code-plugins/)
