# PodCleaner-editor

*[English version](README.md)*

Un outil en ligne de commande qui fait le travail répétitif du montage d'un épisode de podcast, du fichier brut au fichier prêt à finaliser. Il remplace Auphonic pour le traitement du son et prépare le travail manuel restant avec des timecodes.

> **État : début du développement.** Rien n'est encore utilisable. Le premier jalon (analyse et rapport `--dry-run`) est en cours ; voir la [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md).

## Ce qu'il fera

- **Son studio** : débruitage, réduction de la réverb, EQ, compression et de-esser sur chaque piste, puis mixage normalisé à -16 LUFS et -1 dBTP.
- **Blancs** : raccourcit à environ 0,4 s tout silence de plus de 1 s où toutes les pistes se taisent, avec un fondu.
- **Hésitations** : retire les « euh » isolés qui ne cassent pas la phrase, signale les autres.
- **Paroles qui se chevauchent** : pose un timecode chaque fois qu'une personne tente de parler par-dessus l'autre sans prendre la parole.
- **Marqueurs vocaux** : repère les consignes dites à voix haute, comme « Claude ici on veut couper » ou « Claude ici on veut ajouter un extrait ».
- **Extraits de film** : repère chaque passage diffusé pendant l'enregistrement, grâce à l'activité sur la piste film.
- **Suggestions de coupe** : propose des passages à retirer, avec la raison (optionnel, passe par l'API Claude).

Le mode `--dry-run` écrit le rapport et les timecodes sans toucher à l'audio.

## Sorties

- Une piste traitée par personne et la piste film, coupées aux mêmes endroits pour rester synchronisées, plus un mixage stéréo.
- Un fichier de montage Markdown par épisode : les timecodes (sur l'audio original et sur l'audio final) et un rapport (loudness avant et après, ce qui a été retiré, ce qui a été signalé).
- Des marqueurs dans un fichier MIDI et dans le WAV du mixage, pour Logic Pro et Cakewalk.

## Principes

- **Tout en local d'abord.** Le traitement du signal tourne en local avec des outils open source (ffmpeg, DeepFilterNet, Silero VAD, Whisper). Aucun compte ni clé d'API n'est nécessaire.
- **Claude est optionnel.** Avec une clé d'API, Claude lit la transcription horodatée (jamais l'audio) pour trancher là où une règle fixe échoue. Chacun de ses avis est journalisé dans le fichier de montage.
- **macOS et Windows.**

## Prérequis

- Python 3.11 ou 3.12, géré avec [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) dans le `PATH` (`brew install ffmpeg` sur macOS, `winget install ffmpeg` sur Windows)
- En entrée : fichiers WAV uniquement ; deux pistes voix (une par personne) et une piste film

Les instructions d'installation et d'utilisation arriveront avec la première version.

## Documentation

| Document | English | Français |
| --- | --- | --- |
| Cadrage du projet | [docs/spec.md](docs/spec.md) | [docs/spec.fr.md](docs/spec.fr.md) |
| Feuille de route | [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md) | [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md) |
| Plan du jalon 1 | [M1 plan](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.md) | [plan M1](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.fr.md) |
| Contribuer | [CONTRIBUTING.md](CONTRIBUTING.md) | [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md) |

## Licence

[MIT](LICENSE)
