# Journal des versions

**Français** · [English](CHANGELOG.md)

Tous les changements notables de podcleaner-editor. Les versions suivent le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Ajouts

- Son studio dans `pedit run` : chaque piste de voix passe par DeepFilterNet 3 (bruit et réverb), puis par des filtres ffmpeg (passe-haut, EQ, compresseur) ; le film reçoit son propre gain jusqu'au volume des voix, et un limiteur sur chaque piste, un autre lié entre elles et un seul gain commun à toutes les pistes et au mixage amènent le mixage à -16 LUFS sans dépasser -1 dBTP. Le fichier de montage a une section `### Sound` (chaîne, gain du film, gain commun, volume et pic réel de chaque fichier avant et après). La section `[sound]` de la configuration la règle (`enabled`, `denoise`, `filters`, `target_lufs`, `true_peak_db`). Le modèle DeepFilterNet est téléchargé au premier lancement.
- Un test lent sur l'enregistrement de test : volume et pic réel du mixage, et équilibre des bandes face à la version Auphonic.
- `pedit run` sans `--dry-run` écrit l'audio monté : une piste par voix (ou la piste des voix mélangées) et la piste film, coupées aux mêmes échantillons avec un fondu enchaîné à puissance constante (30 ms) à chaque raccord, un mixage stéréo, et les marqueurs dans un fichier MIDI et dans le WAV du mixage, chacun nommé par son seul type (`Requested cut`, `Clip to add`, `Film clip`, `Overlap`, `Hesitation` pour un « euh » qui n'a pas pu être coupé). Le fichier de montage liste les fichiers écrits et ses timecodes « Final » tombent sur l'audio.
- Une porte sur chaque piste de voix, comme Strip Silence de Logic Pro (-30 dB, 0,5 s, attaque 10 ms, relâchement 0,1 s), décidée sur le niveau sonore avec le test de repisse ; la section `[gate]` de la configuration la règle ou la coupe.
- Écriture sûre : les fichiers sont écrits sous un nom temporaire puis renommés, jamais laissés à moitié écrits après une erreur ; la place sur le disque est vérifiée d'abord, et des pistes de fréquences différentes ou de plus de 2 canaux arrêtent la commande avec une erreur claire.
- `pedit run --dry-run` transcrit désormais les passages où quelqu'un parle (Whisper : mlx-whisper sur Apple silicon, faster-whisper ailleurs ; le modèle, environ 1,6 Go, est téléchargé au premier lancement) et garde les mots dans `<nom>.words.json` : un second lancement ne retranscrit pas.
- Hésitations : chaque « euh » isolé est retiré, les autres (une autre voix ou un autre mot en même temps, un extrait de film, trop long) sont signalés dans le fichier de montage avec les mots autour.
- Marqueurs vocaux : une consigne parlée à Claude (un appel en début de phrase, « dis Claude » ou « Claude » suivi d'une virgule ou d'une pause, puis un verbe d'action comme « couper » ou « ajouter ») devient un événement `Requested cut` ou `Clip to add` et un marqueur ; la consigne reste dans l'audio, à couper à la main (`[markers] cut_instructions = true` la coupe quand personne ne parle par-dessus).
- Le rapport du fichier de montage indique désormais les hésitations, les marqueurs et la transcription (moteur, parole transcrite, pistes lues dans le cache).
- `pedit run --dry-run` : lit un épisode (un WAV par voix, ou les deux voix sur un WAV stéréo, plus la piste film) et écrit son fichier de montage : extraits de film, tentatives de parler par-dessus l'autre (pistes séparées seulement), longs blancs à raccourcir, avec les timecodes sur l'audio original et sur l'audio monté.
- `pedit init` : quelques questions (dossier de sortie, forme d'enregistrement, prénoms des voix, Claude), puis le fichier de configuration commenté ; `pedit config` l'affiche.
- Titre en pixel art aux couleurs du podcast au lancement de l'outil dans un terminal.
- Cahier des charges, feuille de route et plans des jalons 1 et 2, en anglais et en français.
- Règles du dépôt : `main` protégée, pull requests approuvées par le mainteneur, Conventional Commits en anglais puis en français.

### Modifié

- Python 3.11 seulement (`>=3.11,<3.12`) : DeepFilterNet n'a pas de paquet pour 3.12 sur Mac Apple silicon. La CI ne teste plus 3.12.
