# podcleaner-editor

**Français** · [English](README.md)

Un outil en ligne de commande qui fait le travail répétitif du montage d'un épisode de podcast, du fichier brut aux pistes prêtes à finaliser à la main dans Logic Pro. Il remplace Auphonic pour le son et prépare le travail manuel restant avec des timecodes.

> **État : début du développement.** Rien n'est encore utilisable. Le premier jalon (analyse et rapport `--dry-run`) est en cours ; voir la [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md).

## Ce qu'il fera

- **Son studio** : débruitage, réduction de la réverb, EQ, compression et de-esser sur chaque piste, puis mixage normalisé à -16 LUFS et -1 dBTP.
- **Blancs** : raccourcit à environ 0,4 s tout silence de plus de 1 s où toutes les pistes se taisent, avec un fondu.
- **Hésitations** : retire les « euh » isolés qui ne cassent pas la phrase, signale les autres.
- **Paroles qui se chevauchent** : pose un timecode chaque fois qu'une personne tente de parler par-dessus l'autre sans prendre la parole.
- **Marqueurs vocaux** : repère les consignes dites à voix haute, comme « Claude ici on veut couper » ou « Claude ici on veut ajouter un extrait ».
- **Extraits de film** : repère chaque passage diffusé pendant l'enregistrement, grâce à l'activité sur la piste film.
- **Suggestions de coupe** : propose des passages à retirer, avec la raison (avec Claude).

Le mode `--dry-run` écrit le rapport et les timecodes sans toucher à l'audio.

## Deux formes d'enregistrement

| Forme | Tu fournis | À savoir |
| --- | --- | --- |
| Pistes séparées | un WAV par voix + le WAV de la piste film | tout ce qui précède |
| Voix mélangées | un WAV stéréo avec les deux voix + le WAV de la piste film | les chevauchements ne peuvent être ni repérés ni coupés, un « euh » n'est retiré que si personne d'autre ne parle en même temps, une seule chaîne de son pour les deux voix |

## Sorties

- Les pistes voix traitées et la piste film, coupées aux mêmes endroits pour rester synchronisées, plus un mixage stéréo.
- Un fichier de montage Markdown par épisode : les timecodes (sur l'audio original et sur l'audio final) et un rapport (loudness avant et après, ce qui a été retiré, ce qui a été signalé).
- Des marqueurs dans un fichier MIDI et dans le WAV du mixage, pour Logic Pro et Cakewalk.

## Commandes

Interface prévue, disponible à partir du jalon 1 :

```bash
uv tool install git+https://github.com/IvesPower/podcleaner-editor
pedit init       # quelques questions, puis écrit ton fichier de configuration
pedit run --voice julien.wav --voice marc.wav --film film.wav --out episode-42 --dry-run
pedit config     # affiche la configuration (--path : seulement son emplacement)
```

`podcleaner-editor` et son alias court `pedit` sont la même commande. Dans un terminal, elle commence par son titre en pixel art. Le programme s'affiche en anglais.

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
| Journal des versions | [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG.fr.md](CHANGELOG.fr.md) |

## Contribuer

Les pull requests sont les bienvenues. `main` est protégée et chaque PR est approuvée par le mainteneur. Les commits et les titres de PR suivent Conventional Commits, en anglais puis en français. Voir [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md).

## Licence

[MIT](LICENSE)
