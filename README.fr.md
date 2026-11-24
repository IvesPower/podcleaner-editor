# podcleaner-editor

**Français** · [English](README.md)

Un outil en ligne de commande qui fait le travail répétitif du montage d'un épisode de podcast, du fichier brut aux pistes prêtes à finaliser à la main dans Logic Pro. Il remplace Auphonic pour le son et prépare le travail manuel restant avec des timecodes.

> **État : début du développement.** Le montage fonctionne (jalons 1 à 3 : blancs, chevauchements, extraits de film, transcription, hésitations, marqueurs vocaux, puis les pistes montées, le mixage et les marqueurs) ; le son studio et les avis de Claude restent à venir. Voir la [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md).

## Ce qu'il fera

- **Son studio** : débruitage, réduction de la réverb, EQ, compression et de-esser sur chaque piste, puis mixage normalisé à -16 LUFS et -1 dBTP.
- **Blancs** : raccourcit à environ 0,4 s tout silence de plus de 1 s où toutes les pistes se taisent, avec un fondu.
- **Hésitations** : retire les « euh » isolés qui ne cassent pas la phrase, signale les autres.
- **Paroles qui se chevauchent** : pose un timecode chaque fois qu'une personne tente de parler par-dessus l'autre sans prendre la parole.
- **Marqueurs vocaux** : repère les consignes dites à voix haute à Claude, un appel en début de phrase, « dis Claude » ou « Claude » suivi d'une virgule ou d'une pause (pour qu'un prénom comme « Claude Chabrol » ne compte pas), puis un verbe d'action, comme « Dis Claude, on va couper ce passage-là » ou « Claude, ajoute un extrait ici », et retire la consigne elle-même de l'audio.
- **Extraits de film** : repère chaque passage diffusé pendant l'enregistrement, grâce à l'activité sur la piste film.
- **Suggestions de coupe** : propose des passages à retirer, avec la raison (avec Claude).

Le mode `--dry-run` écrit le rapport et les timecodes sans toucher à l'audio.

## Deux formes d'enregistrement

| Forme | Tu fournis | À savoir |
| --- | --- | --- |
| Pistes séparées | un WAV par voix + le WAV de la piste film | tout ce qui précède |
| Voix mélangées | un WAV stéréo avec les deux voix + le WAV de la piste film | les chevauchements ne peuvent être ni repérés ni coupés, un « euh » n'est retiré que si personne d'autre ne parle en même temps, une seule chaîne de son pour les deux voix |

## Sorties

- Les pistes de voix, passées à la porte comme Strip Silence de Logic Pro (silence numérique là où la personne ne parle pas), et la piste film, toutes coupées aux mêmes endroits avec un fondu enchaîné à chaque raccord pour rester synchronisées, plus un mixage stéréo (une simple somme, pas encore normalisée).
- Un fichier de montage Markdown par épisode : les timecodes (sur l'audio original et sur l'audio final) et un rapport (loudness avant et après, ce qui a été retiré, ce qui a été signalé).
- Des marqueurs dans un fichier MIDI et dans le WAV du mixage, pour Logic Pro et Cakewalk.

## Installer

```bash
brew install ffmpeg            # macOS (Windows : winget install ffmpeg)
uv tool install git+https://github.com/IvesPower/podcleaner-editor
```

`podcleaner-editor` et son alias court `pedit` sont la même commande. Le programme s'affiche en anglais. Dans un terminal, il commence par son titre en pixel art (`--no-banner` ou `PODCLEANER_EDITOR_NO_BANNER=1` pour le masquer).

## Configurer

```bash
pedit init            # quelques questions, puis écrit ton fichier de configuration
pedit config          # affiche la configuration telle qu'elle est lue, défauts compris
pedit config --path   # seulement l'emplacement du fichier
```

`pedit init` demande le dossier des épisodes montés, ta façon d'enregistrer (un fichier par voix, ou les deux voix sur un fichier stéréo), les prénoms des deux voix, et s'il faut utiliser Claude ; il vérifie que Claude Code est installé et connecté. Tes réponses actuelles sont proposées par défaut quand tu le relances. Tous les autres réglages sont dans le fichier, commentés. `pedit init --no-input` écrit le fichier commenté sans poser de questions.

## Lancer

Sans `--dry-run`, `run` écrit aussi l'audio monté ; avec `--dry-run`, il n'écrit que le fichier de montage.

```bash
# Un fichier par voix
pedit run --voice julien.wav --voice franck.wav --film film.wav --out "Episode 42"

# Les deux voix sur un seul fichier stéréo
pedit run --voice voix.wav --film film.wav --out "Episode 42"

# Analyse seule : le fichier de montage, sans audio
pedit run --voice julien.wav --voice franck.wav --film film.wav --out "Episode 42" --dry-run
```

La commande écrit `Episode 42/Episode 42.edit.md` : les marqueurs vocaux, les extraits de film et les tentatives de parler par-dessus l'autre, avec leurs timecodes sur l'audio original et sur l'audio monté ; puis un rapport : les longs blancs et les « euh » qui seront retirés, les « euh » seulement signalés (avec leurs timecodes et les mots autour), et ce qui a été transcrit. `--name` donne le nom de l'épisode (par défaut, le nom du dossier `--out`). Avec un dossier de sortie réglé par `pedit init`, `--name "Episode 42"` suffit : les fichiers vont dans `<dossier de sortie>/Episode 42/`.

Seuls les passages où quelqu'un parle sont transcrits, avec Whisper (mlx-whisper sur Apple silicon, faster-whisper ailleurs). Le premier lancement télécharge le modèle Whisper, environ 1,6 Go, une seule fois. Les mots entendus sont gardés dans `Episode 42/Episode 42.words.json` : relancer sur les mêmes fichiers ne retranscrit pas.

La commande écrit aussi, dans le même dossier :

- `Episode 42.<voix>.wav` : une piste par voix (une seule pour les deux voix si elles arrivent mélangées), passée à la porte et coupée, au format des bruts ;
- `Episode 42.film.wav` : la piste film, coupée aux mêmes endroits, sans porte ;
- `Episode 42.mix.wav` : le mixage stéréo, avec les marqueurs inscrits dedans ;
- `Episode 42.markers.mid` : les marqueurs seuls, dans un fichier MIDI.

Un épisode de 2 h 10 pèse environ 2,3 Go par piste ; le programme vérifie d'abord la place libre sur le disque, et une erreur ne laisse aucun fichier à moitié écrit.

### Importer dans Logic Pro

1. Glisser les pistes (`.<voix>.wav` et `.film.wav`) dans le projet, toutes au début : elles ont la même durée et restent synchronisées.
2. Les marqueurs : soit **Fichier > Importer > Fichier MIDI** avec `Episode 42.markers.mid`, soit **Importer les marqueurs depuis un fichier audio** sur le mixage. Lequel des deux tombe le mieux reste à confirmer dans Logic.

À venir : le son studio (M4) et les avis de Claude (M5).

## Claude, en option

Tout le traitement du signal tourne en local avec des outils open source (ffmpeg, DeepFilterNet, Silero VAD, Whisper). Si [Claude Code](https://claude.com/claude-code) est installé et connecté (`claude auth login`), l'outil demande à Claude, par ton abonnement Claude et jamais par une clé d'API, de trancher là où une règle fixe échoue. Claude lit la transcription horodatée, jamais l'audio, et chacun de ses avis est journalisé dans le fichier de montage. Sans Claude Code, des règles fixes s'appliquent.

## Prérequis

- macOS ou Windows
- Python 3.11 ou 3.12, avec [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) dans le `PATH` (`brew install ffmpeg` sur macOS, `winget install ffmpeg` sur Windows)
- En entrée : fichiers WAV uniquement

## Documentation

| Document | English | Français |
| --- | --- | --- |
| Cahier des charges | [docs/spec.md](docs/spec.md) | [docs/spec.fr.md](docs/spec.fr.md) (fait foi) |
| Feuille de route | [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md) | [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md) |
| Plan du jalon 1 | [M1 plan](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.md) | [plan M1](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.fr.md) |
| Plan du jalon 2 | [M2 plan](docs/superpowers/plans/2026-11-22-m2-transcription-markers.md) | [plan M2](docs/superpowers/plans/2026-11-22-m2-transcription-markers.fr.md) |
| Journal des versions | [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG.fr.md](CHANGELOG.fr.md) |

## Contribuer

Les pull requests sont les bienvenues. `main` est protégée et chaque PR est approuvée par le mainteneur. Les commits et les titres de PR suivent Conventional Commits, en anglais puis en français. Voir [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md).

## Licence

[MIT](LICENSE)
