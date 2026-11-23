# Journal des versions

**Français** · [English](CHANGELOG.md)

Tous les changements notables de podcleaner-editor. Les versions suivent le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Ajouts

- `pedit run --dry-run` transcrit désormais les passages où quelqu'un parle (Whisper : mlx-whisper sur Apple silicon, faster-whisper ailleurs ; le modèle, environ 1,6 Go, est téléchargé au premier lancement) et garde les mots dans `<nom>.words.json` : un second lancement ne retranscrit pas.
- Hésitations : chaque « euh » isolé est retiré, les autres (une autre voix ou un autre mot en même temps, un extrait de film, trop long) sont signalés dans le fichier de montage avec les mots autour.
- Marqueurs vocaux : une consigne parlée à Claude (un appel en début de phrase, « dis Claude » ou « Claude » suivi d'une virgule ou d'une pause, puis un verbe d'action comme « couper » ou « ajouter ») devient un événement `Requested cut` ou `Clip to add`, et la consigne elle-même est retirée quand personne ne parle par-dessus ; une consigne sans fin nette en 15 s reste dans l'audio.
- Le rapport du fichier de montage indique désormais les hésitations, les marqueurs et la transcription (moteur, parole transcrite, pistes lues dans le cache).
- `pedit run --dry-run` : lit un épisode (un WAV par voix, ou les deux voix sur un WAV stéréo, plus la piste film) et écrit son fichier de montage : extraits de film, tentatives de parler par-dessus l'autre (pistes séparées seulement), longs blancs à raccourcir, avec les timecodes sur l'audio original et sur l'audio monté.
- `pedit init` : quelques questions (dossier de sortie, forme d'enregistrement, prénoms des voix, Claude), puis le fichier de configuration commenté ; `pedit config` l'affiche.
- Titre en pixel art aux couleurs du podcast au lancement de l'outil dans un terminal.
- Cahier des charges, feuille de route et plans des jalons 1 et 2, en anglais et en français.
- Règles du dépôt : `main` protégée, pull requests approuvées par le mainteneur, Conventional Commits en anglais puis en français.
