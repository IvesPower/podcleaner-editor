# Journal des versions

**Français** · [English](CHANGELOG.md)

Tous les changements notables de podcleaner-editor. Les versions suivent le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Ajouts

- `pedit run --dry-run` : lit un épisode (un WAV par voix, ou les deux voix sur un WAV stéréo, plus la piste film) et écrit son fichier de montage : extraits de film, tentatives de parler par-dessus l'autre (pistes séparées seulement), longs blancs à raccourcir, avec les timecodes sur l'audio original et sur l'audio monté.
- `pedit init` : quelques questions (dossier de sortie, forme d'enregistrement, prénoms des voix, Claude), puis le fichier de configuration commenté ; `pedit config` l'affiche.
- Titre en pixel art aux couleurs du podcast au lancement de l'outil dans un terminal.
- Cahier des charges, feuille de route et plan du jalon 1, en anglais et en français.
- Règles du dépôt : `main` protégée, pull requests approuvées par le mainteneur, Conventional Commits en anglais puis en français.
