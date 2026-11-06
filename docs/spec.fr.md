# PodCleaner-editor : montage podcast automatisé, idée de base

*[English version](spec.md)*

Nov 5, 2026 · @Julien

## Contexte et objectif

L'objectif est un outil en ligne de commande qui fait le travail répétitif du montage d'un épisode, du fichier brut au fichier prêt à finaliser. Il remplace Auphonic pour le traitement du son et prépare le travail manuel restant avec des timecodes.

L'outil tourne sur macOS et Windows et sera publié en open source sur un dépôt Git. Il doit rester utilisable sans compte ni clé d'API : les fonctions qui passent par Claude sont un plus, pas un prérequis.

## Fonctionnalités

| Fonctionnalité | Ce qu'elle fait | Outils open source | Apport de Claude |
| --- | --- | --- | --- |
| Son studio | Débruitage, réduction de la réverb, EQ, compression, de-esser sur chaque piste, puis mixage normalisé à -16 LUFS et -1 dBTP | ffmpeg, DeepFilterNet, nara\_wpe | Choisir les réglages à partir des mesures de chaque piste |
| Blancs | Raccourcit à environ 0,4 s tout silence de plus de 1 s où toutes les pistes se taisent, avec un fondu | Silero VAD par piste, ffmpeg | Aucun |
| Hésitations | Retire les « euh » isolés qui ne cassent pas la phrase, signale les autres | faster-whisper ou mlx-whisper (timestamps par mot), piste par piste | Juger, phrase par phrase, si une coupe reste naturelle |
| Paroles qui se chevauchent | Repère une personne qui tente de parler par-dessus une autre sans prendre la parole ; pose un timecode, le traitement se fait à la main | Chevauchements détectés par VAD sur chaque piste | Écarter les relances (« oui », « mmh ») et les rires pour ne signaler que les vraies tentatives |
| Marqueurs vocaux | Repère « Claude ici on veut couper » et « Claude ici on veut ajouter un extrait » | Whisper + recherche floue (rapidfuzz) | Reconnaître les variantes de formulation |
| Extraits de film | Repère chaque passage diffusé, grâce à l'activité sur la piste film | Détection d'activité sur la piste dédiée | Aucun |
| Suggestions de coupe | Propose des passages à retirer, avec la raison | Aucun | Lecture de la transcription, guidée par des exemples tirés des épisodes déjà montés |

Le mode `--dry-run` produit le rapport et les timecodes sans modifier l'audio, pour valider les réglages sur les premiers épisodes.

## Architecture

Le programme est une CLI Python qui fait tout le traitement en local. Claude s'y ajoute à deux endroits, toujours en option : l'API pour les décisions qui demandent du jugement, et des skills pour piloter l'outil en langage naturel.

*Schéma d'architecture : cœur local, deux couches Claude optionnelles (voir la liste ci-dessous).*

Les traits pointillés marquent ce qui est optionnel. Sans clé d'API, l'étape Décisions applique seulement des règles fixes.

- **Les outils open source gardent le traitement du signal.** Claude n'écoute pas l'audio : il lit la transcription horodatée et les mesures. Le débruitage, la normalisation et les coupes restent dans ffmpeg et les modèles locaux, ce qui les rend gratuits et reproductibles.
- **Claude intervient là où une règle échoue.** Savoir si un « euh » peut sauter sans casser la phrase, reconnaître un marqueur mal transcrit, repérer un passage hors sujet : ce sont des jugements sur le sens, pas sur le signal.
- **Les skills enveloppent la CLI, ils ne la remplacent pas.** Un skill ne tourne que dans Claude Code. La CLI doit donc fonctionner seule, pour les contributeurs du dépôt et pour l'automatisation. Le dossier `skills/` du dépôt contient ensuite des skills qui l'appellent : montage complet, relecture du rapport, réglage d'un épisode difficile.

Points de vigilance, pour des épisodes d'environ 2 h 10 :

- **Temps de calcul.** Chaque piste fait 2 h 10. On ne transcrit que les passages où la piste est active, ce qui réduit nettement le volume. Sur un Mac Apple Silicon ou un PC avec carte NVIDIA, c'est raisonnable ; sur un processeur seul, il faut prévoir de lancer le traitement et le laisser tourner.
- **Taille envoyée à Claude.** Pour les suggestions de coupe, la transcription horodatée par phrase d'un épisode entier tient en un appel. Pour juger les « euh », on n'envoie que la phrase autour de chaque candidat, sans les timestamps par mot de tout l'épisode.
- **Coût par épisode**, à mesurer sur le premier épisode test.
- **Reproductibilité** : les avis rendus par Claude sont journalisés dans le fichier de montage.

## Sorties produites

- **Pistes finales** : une piste traitée par personne et la piste film, coupées aux mêmes endroits pour rester synchronisées, prêtes à glisser dans le logiciel de montage. Un mixage stéréo est aussi produit.
- **Fichier de montage (.md)** : un seul fichier Markdown par épisode, en deux parties.
  - Timecodes : chaque événement avec son type (coupe demandée, extrait à ajouter, extrait de film, chevauchement, suggestion), le timecode sur l'audio original et sur l'audio final, et la raison.
  - Rapport : les mesures avant et après (LUFS, true peak) par piste, le nombre de blancs et d'hésitations retirés, les « euh » signalés sans être coupés, et les avis rendus par Claude.
- **Marqueurs** : un fichier MIDI qui ne contient que les marqueurs, et les mêmes marqueurs inscrits dans le WAV du mixage. Logic Pro et Cakewalk savent lire l'un ou l'autre ; le bon format est à confirmer en test sur chaque logiciel.

Toutes les analyses se font sur l'audio original. Le programme garde la carte des coupes pour recaler chaque timecode sur le fichier final.

## Hors périmètre, décisions et questions ouvertes

La première version ne fait pas le montage créatif (choix des extraits, ordre des séquences, habillage sonore) ni la publication de l'épisode.

| Sujet | Décision |
| --- | --- |
| Enregistrement | Toujours deux personnes, une piste chacune, plus la piste film |
| Format des bruts | WAV uniquement, à la meilleure qualité d'enregistrement |
| Durée des épisodes | Environ 2 h 10 |
| Extraits de film | Diffusés en direct pendant l'enregistrement, sur une piste séparée |
| Logiciel de montage | Logic Pro |
| Référence pour le son | Plusieurs épisodes bruts avec leur version traitée par Auphonic |
| Référence pour le style | Plusieurs dizaines d'heures d'épisodes montés, avec leurs bruts sans les extraits de film |
| Chevauchements | Timecode seul, aucune baisse de volume automatique |
| Fichier de sortie | Un seul .md par épisode : timecodes et rapport |
| API Claude | La transcription peut lui être envoyée |

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
- **Test rapide** : fait tourner toute la chaîne sur un extrait de 10 minutes des deux pistes et de la piste film, pour vérifier une modification sans traiter 2 h 10.
- **Compatibilité Windows** : vérifie les chemins, la présence de ffmpeg et l'encodage des fichiers avant chaque version.

Un fichier `CLAUDE.md` à la racine reprend les décisions de ce document. Claude Code le relit au début de chaque session.

Sources : [Dupple, meilleurs skills Claude Code 2026](https://dupple.com/learn/best-claude-code-skills-2026) · [Redwerk, meilleurs plugins Claude Code 2026](https://redwerk.com/blog/best-claude-code-plugins/)
