# podcleaner-editor

CLI Python qui fait le travail répétitif du montage d'un épisode de podcast : son studio, blancs, hésitations, chevauchements, marqueurs vocaux, extraits de film, et un fichier de montage avec les timecodes pour Logic Pro. Remplace Auphonic.

- Cahier des charges : `docs/spec.fr.md` (original, fait foi) · `docs/spec.md` (anglais)
- Feuille de route : `docs/superpowers/plans/2026-11-05-roadmap.fr.md` (et `.md` en anglais)
- Plan du jalon en cours : `docs/superpowers/plans/2026-11-28-m4-studio-sound.fr.md` (et `.md` en anglais), conception : `docs/superpowers/specs/2026-11-28-m4-studio-sound-design.fr.md`

## Commandes

La CLI fait `init`, `config`, `run` et `version` ; `run` sans `--dry-run` écrit les pistes montées, le mixage et les marqueurs (jalon M3) et le son studio des voix (jalon M4 : DeepFilterNet 3, filtres ffmpeg, film mis au niveau des voix, gain commun et limiteur lié) ; `--dry-run` ne traite pas le son. Python 3.11 seulement.

```bash
# Essai sur l'enregistrement de test (samples/pedit, lien local hors git)
uv run pedit run --voice samples/pedit/pedit-full-piste-1-julien.wav \
  --voice samples/pedit/pedit-full-piste-2-franck.wav \
  --film samples/pedit/pedit-full-piste-3-film.wav --out out/pedit --dry-run
```

```bash
uv sync                    # installer
uv run pytest              # tests rapides (sans modèle ni réseau)
uv run pytest -m slow      # tests qui chargent un modèle (Silero, Whisper)
uv run ruff check          # lint
uv run ruff format         # formatage
uv run pedit               # la CLI (alias court de podcleaner-editor)
```

Le hook `.claude/hooks/python_checks.py` lance Ruff et les tests rapides après chaque modification d'un `.py`.

## Règles du dépôt

- `main` est protégée : on travaille sur une branche (`feat/…`, `fix/…`, `docs/…`, `chore/…`, `test/…`, `ci/…`, `refactor/…`) et tout arrive par une pull request, approuvée par le propriétaire (CODEOWNERS).
- Messages de commit au format Conventional Commits, **en anglais puis en français** :
  - titre : `type(portée): English summary / résumé en français` (ex. `feat(silences): shorten long silences / raccourcir les longs blancs`) ;
  - corps facultatif : un paragraphe en anglais, une ligne vide, le même en français.
- Titre de PR : même format que le titre de commit (`type: English / français`).
- Description de PR : **tout en anglais d'abord, puis tout en français**, séparés par `---`. Chaque version commence par son `## TL;DR` : 1 à 3 phrases simples qui disent ce que change la PR et pourquoi, compréhensibles sans lire le code. Suivre `.github/pull_request_template.md`.
- Documentation en anglais (`*.md`) et en français (`*.fr.md`) : toute modification de l'une met l'autre à jour dans la même PR. Ce fichier-ci est en français uniquement.
- Code et sorties en anglais : identifiants, commentaires, docstrings, messages affichés, erreurs, aide de la CLI, fichier de montage, clés du fichier de configuration. Seuls les mots des marqueurs vocaux (le déclencheur « Claude » et les verbes d'action « couper », « ajouter »…), les mots d'hésitation et l'invite de Whisper restent en français : ce sont des paroles à reconnaître.

## Décisions du cahier des charges

| Sujet | Décision |
| --- | --- |
| Plateformes | macOS et Windows ; chemins via `pathlib`, jamais de chemin en dur ; texte en `encoding="utf-8"` |
| Sans Claude | Tout fonctionne sans Claude : chaque appel a un repli par règle fixe |
| Accès à Claude | Compte intégré uniquement : CLI Claude Code connectée (abonnement), jamais de clé d'API ni de SDK `anthropic`. La CLI est lancée sans outils, sans session gardée, sans réglages ni MCP, depuis un dossier temporaire, sans `ANTHROPIC_API_KEY` ; une erreur arrête de la solliciter pour le reste du passage (même fonctionnement que podcleaner-clips) |
| Formes d'enregistrement | `separate` : deux WAV voix + WAV film ; `mixed` : un WAV stéréo des deux voix + WAV film. Avec `mixed`, pas de chevauchements, « euh » retirés seulement sans autre parole en même temps, une seule chaîne de traitement |
| Format des bruts | WAV uniquement |
| Durée des épisodes | Environ 2 h 10 : analyse sur une copie mono 16 kHz, jamais l'audio pleine résolution en mémoire |
| Blancs | Tout silence > 1 s où toutes les pistes se taisent est ramené à ~0,4 s, avec un fondu |
| Chevauchements | Timecode seul, aucune baisse de volume |
| Son | Par piste de voix : DeepFilterNet 3 (bruit et réverb) puis filtres ffmpeg (passe-haut, EQ, compresseur, `[sound] filters`) ; le film mis au niveau des voix (son propre gain), puis un gain commun et un limiteur lié (une seule enveloppe sur toutes les pistes, réglé 0,5 dB sous le plafond) pour un mixage à -16 LUFS et -1 dBTP ; le fichier de montage dit le travail du limiteur ; section `### Sound` avec les mesures avant/après ; WPE écarté ; Python 3.11 seulement (DeepFilterNet) ; banc d'essai contre une seule paire brut / Auphonic pour l'instant |
| Sorties | Pistes coupées aux mêmes endroits à l'échantillon près avec fondu enchaîné de 30 ms à chaque raccord (`<nom>.<voix>.wav`, `<nom>.film.wav`), mixage stéréo `<nom>.mix.wav` (somme exacte des pistes écrites), un seul fichier de montage `.md` (Timecodes + Report), marqueurs MIDI (`<nom>.markers.mid`) et dans le WAV du mixage ; écriture sous nom temporaire puis renommage, place disque vérifiée |
| Porte | Sur chaque piste de voix (pas le film), comme Strip Silence de Logic : -30 dB, 0,5 s, attaque 10 ms, relâchement 0,1 s (`[gate]`), décidée sur le niveau avec le test de repisse, calculée par `analyze()` ; valeurs non encore validées à l'oreille |
| Analyses | Toujours sur l'audio original ; la carte des coupes recale les timecodes sur le final |
| `--dry-run` | Rapport et timecodes, aucun audio écrit |

## Interface de la CLI

| Sujet | Décision |
| --- | --- |
| Paquet / commande | `podcleaner_editor` / `podcleaner-editor` et son alias `pedit` (`init`, `run`, `config [--path]`, `version`, `--version`). Installation : `uv tool install git+https://github.com/IvesPower/podcleaner-editor` |
| Bannière | Nom en pixel art (demi-blocs, lettres #fbf2f1 sur pastille #94380c, couleurs du podcast, comme podcleaner-clips) au début de `init`, `run` et de la commande seule ; jamais hors terminal ; `--no-banner` ou `PODCLEANER_EDITOR_NO_BANNER=1` ; titre sur une ligne si le terminal est trop étroit ou ne sait pas afficher les blocs |
| Assistant `init` | Pose les questions (dossier de sortie, forme d'enregistrement, prénoms des voix, Claude) et écrit le modèle commenté avec les réponses ; valeurs actuelles proposées par défaut, remplacement après confirmation, écriture atomique ; hors terminal ou `--no-input` : modèle commenté sans questions |
| Configuration | TOML dans `platformdirs.user_config_dir("podcleaner-editor")/config.toml`, remplaçable par `--config` ou `PODCLEANER_EDITOR_CONFIG` |
| Erreurs | `EditorError` : message `Error: …` sur stderr, code de sortie 2, jamais de trace Python |

## Réglages validés sur l'enregistrement de test

`samples/pedit` (75 s, Julien et Franck, gate au silence numérique entre les phrases), relu avec Julien le 22 nov. 2026 :

| Réglage | Valeur | Pourquoi |
| --- | --- | --- |
| `[overlaps] min_s` | 0,15 s | Les trois tentatives de Franck durent 0,17 à 0,6 s ; la règle signale large, Claude (M5) écartera les relances |
| `[overlaps] floor_hold_s` | 0,5 s | Julien reprend 0,5 s après la dernière tentative |
| `[overlaps] merge_gap_s` | 0,5 s | Une pause de 0,3 s de Julien ne termine pas son tour |
| `[levels] own_speech_gap_s` | 0,2 s | Le filtre de repisse, trame par trame, coupe entre les syllabes |
| Bruit de fond | silence numérique exclu | Sinon plancher à -120 dB et chaque souffle compte comme un son fort |
| Marqueurs vocaux (`[markers]`) | appel explicite en début de phrase : « dis Claude » (« dis » en début de phrase, une hésitation devant ne compte pas) ou « Claude » suivi d'une virgule ou d'une pause ; puis verbe d'action (`cut_words`, `clip_words`) ; `min_score` 80, `pause_s` 0,5 s, `max_s` 15 s mesuré depuis « dis » ; la consigne reste dans l'audio (`cut_instructions = false`), Julien la coupe lui-même ; marqueurs MIDI et WAV nommés par leur seul type (`Requested cut`, `Hesitation`…) | Sur l'enregistrement de test, Julien donne des consignes parlées (« Dis Claude, on va couper ce passage-là… »), pas des phrases fixes ; règle choisie par Julien le 22 nov. 2026, appel explicite décidé le 23 nov. 2026 pour qu'un prénom (« Claude Chabrol ») ne compte pas ; après écoute le 28 nov. 2026, couper la consigne rendait le passage incompréhensible |
| Hésitations (`[hesitations]`) | valeurs par défaut | Les 6 « euh » trouvés sont tous ceux que Julien entend |

Résultat attendu : 3 chevauchements (47,7 s, 50,2 s, 50,8 s), 1 extrait de film (62,3 – 67,4 s), 3 marqueurs (18,7 s Clip to add, 27,6 s Requested cut, 40,3 s Requested cut, consignes gardées dans l'audio), 3 « euh » coupés sur Julien (13,2 s, 26,9 s, 39,7 s) et 3 signalés sur Franck (48,0 s, 50,9 s, 51,3 s, parole de Julien en même temps, marqueurs `Hesitation`), 5 blancs raccourcis (6,8 s retirées) ; vérifié par les tests lents de `tests/test_pipeline.py`.

## Points de vigilance

- **Repisse entre micros** : une voix ne compte comme active que si elle dépasse l'autre de `bleed_margin_db`.
- **Rires et respirations** : un blanc exige aussi qu'aucune piste ne dépasse son bruit de fond + 12 dB.
- **Temps de calcul** : on ne transcrit que les passages actifs.
- **Reproductibilité** : les avis de Claude sont écrits dans le fichier de montage.
- **Tests** : les tests rapides n'utilisent ni modèle ni réseau (ffmpeg est permis) ; l'audio de test est généré dans `tmp_path`, sauf les courts extraits de parole de `tests/data/`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
