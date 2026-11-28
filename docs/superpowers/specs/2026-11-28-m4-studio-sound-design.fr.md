# M4 : son studio, conception

**Français** · [English](2026-11-28-m4-studio-sound-design.md)

28 nov. 2026 · après l'écoute du M3 par Julien

## Intention

Julien a écouté le montage du M3 sur l'enregistrement de test : « un bon premier jet », mais il reste un vrai travail sur le son, d'abord sur la réverb. Le modèle à copier est la version Auphonic du même enregistrement (`samples/pedit/pedit-full-ia.mp3`, sans le jingle du début ni celui de la fin). Julien ne connaît pas les réglages : Auphonic était en automatique.

**C'est réussi si**, à l'écoute, les voix des pistes montées et du mixage sonnent comme la version Auphonic : sèches, sans « boîte », au même volume, sans souffle dans les pauses.

## Ce qu'Auphonic fait sur l'enregistrement de test (mesuré le 28 nov. 2026)

| Mesure | Brut | Auphonic |
| --- | --- | --- |
| Ressemblance avec le brut (corrélation, par tranches de 10 s) | — | 0,94 à 0,97 : un traitement fin |
| Énergie changée par rapport au brut | — | -9 dB, réduction de bruit et de réverb, égalisation, volume compris |
| Volume intégré / dynamique (LRA) | -14,4 LUFS / 10 LU | -15,8 LUFS / 4,6 LU |
| Équilibre (par rapport à 800–2000 Hz) | — | ~-3 dB sous 300 Hz, -2 dB vers 300–800 Hz, highs bien plus doux au-dessus de 4 kHz |

Essais du 28 nov. 2026, sur la piste de Julien :

- **WPE** (`nara_wpe`, prévu par la feuille de route) ne change presque rien : -35 à -47 dB. L'enregistrement a peu de traîne longue ; ce que Julien entend est plutôt la couleur de la pièce (premières réflexions, « boîte »).
- **DeepFilterNet 3** change l'énergie de -18 dB : il retire bruit et réverb courte, du même ordre qu'Auphonic.
- DeepFilterNet suivi d'une égalisation, d'un compresseur et d'un réglage du volume (« v5 », dans `out/m4-preview/`) arrive à 1,6 dB en moyenne de l'équilibre d'Auphonic, -16 LUFS, LRA 4,9.

## Objectifs

- Une **chaîne par piste de voix** (ou une seule pour les voix mélangées) : DeepFilterNet (bruit et réverb), puis filtres ffmpeg (passe-haut, égalisation, compresseur, adoucissement des aigus).
- Un **mixage à -16 LUFS et -1 dBTP** : le film reçoit d'abord son propre gain jusqu'au volume des voix, puis un seul gain est appliqué à toutes les pistes ; le mixage reste la somme des pistes, comme au M3.
- Les **mesures avant et après** (LUFS et true peak) par piste dans le fichier de montage, comme le demande le cahier des charges.
- Une chaîne **réglable sans toucher au code** : les filtres ffmpeg sont une clé de la configuration, pour régler à l'oreille.

## Hors objectifs

- Copier Auphonic à l'identique ou ses jingles.
- L'avis de Claude sur les réglages (M5).
- Un banc d'essai automatique sur plusieurs paires brut / Auphonic : une seule paire existe pour l'instant ; on garde le script de mesure dans les tests lents.
- WPE : écarté, il ne change presque rien ici.

## Anti-objectifs

- Des voix métalliques, « sous l'eau » ou avec des débuts de mots mangés : DeepFilterNet trop fort serait pire que la réverb.
- Un mixage qui n'est plus la somme des pistes : Julien finit le montage dans Logic sur les pistes.
- Une piste de 2 h 10 en mémoire, ou un traitement qui dure plus longtemps que l'analyse.
- Un passage sans réseau qui plante au premier téléchargement du modèle sans message clair.

## Contraintes

- **Python 3.11 seulement** : `deepfilterlib` n'a pas de paquet tout fait pour 3.12 sur Mac Apple Silicon, et DeepFilterNet 0.5.6 demande `torch` 2.0.1 / `torchaudio` 2.0.2 (les versions suivantes de torchaudio cassent son import). Le projet passe à `requires-python = ">=3.11,<3.12"`, la CI ne teste plus 3.12. Tout se résout avec les dépendances actuelles (numpy 1.26). *Choix de Claude.*
- Le modèle DeepFilterNet 3 est téléchargé au premier passage ; la ligne de progression l'annonce, comme pour Whisper.
- Tout en flux : DeepFilterNet par tranches de 30 s avec 1 s de recouvrement et un fondu enchaîné de 0,5 s ; ffmpeg lit et écrit en flux.
- `--dry-run` n'écrit toujours aucun audio : pas de traitement du son.

## Approches

| Approche | Ce qu'elle donne | Décision |
| --- | --- | --- |
| **DeepFilterNet + filtres ffmpeg + gain commun** | Le plus proche d'Auphonic aux mesures, rapide (~3 min par piste de 2 h 10), réglable à l'oreille | **Retenue** (Julien : « autant faire le M4 ») |
| WPE + filtres ffmpeg | Pas de dépendance lourde | Écartée : ne change presque rien sur ces enregistrements |
| Seulement ffmpeg (`afftdn`, égalisation, compresseur) | Aucune dépendance | Gardée comme repli quand `denoise = false` ; ne retire pas la réverb |
| Normalisation `loudnorm` sur le mixage seul | Simple | Écartée : le mixage ne serait plus la somme des pistes et perdrait ses marqueurs |

## Ce qui est décidé

### La chaîne d'une piste de voix

1. **DeepFilterNet 3** (bruit et réverb), sur une copie mono à 48 kHz de la piste, remise à sa fréquence et à ses canaux d'origine. Désactivable (`[sound] denoise = false`).
2. **Filtres ffmpeg** (`[sound] filters`), par défaut ceux de « v5 » :
   `highpass=f=100,lowshelf=f=250:g=-4,equalizer=f=500:t=q:w=1:g=-1.5,equalizer=f=2500:t=q:w=1:g=-1,highshelf=f=4500:g=-7,acompressor=threshold=-26dB:ratio=3:attack=10:release=250:makeup=2`
3. Le résultat est écrit dans un fichier temporaire du dossier de sortie (`.<nom>.<voix>.sound.tmp.wav`, float 32 bits), qui remplace le brut comme source de l'écriture du M3, puis il est supprimé.

La piste film n'est pas traitée. La porte et les coupes du M3 s'appliquent ensuite, inchangées ; les analyses restent sur l'audio original.

### Le volume

- On mesure (ffmpeg `ebur128`, true peak) avant les coupes : les blancs ne comptent presque pas dans un volume intégré mesuré avec ses seuils.
- Gain du film = `I(voix traitées) - I(film brut)`, gardé entre -20 et +10 dB (0 si l'un des deux est silencieux) : les extraits de film passent au niveau des voix, comme chez Auphonic. Sur `samples/pedit`, l'extrait brut est 5,4 LU plus fort que la parole et culmine à -1,0 dBTP ; sans ce gain, le true peak bloquait le gain commun à 0 dB et le mixage à -18,7 LUFS.
- Gain `g = target_lufs - I`, `I` mesuré sur la somme des voix traitées et du film à son gain. Un passage fort ferait bloquer `g` par le true peak (sur `samples/pedit`, un moment où les deux micros culminent ensemble bloquait le mixage à -17,7 LUFS) : les pistes passent donc par un limiteur, comme chez Auphonic :
  - chaque voix à `g` et le film brut à `gain du film + g` passent par `volume=…dB,alimiter=limit=…:attack=5:release=50:level=disabled:latency=1` (ffmpeg) vers des fichiers temporaires en flottant ; la limite est un pic d'échantillon 0,5 dB sous `true_peak_db`, et `latency=1` retire le retard de 5 ms du limiteur, pour que les pistes restent sur les timecodes de l'analyse ;
  - les limiteurs retirent un peu de volume aux pics : un gain de rattrapage `target_lufs - I(somme limitée)` est appliqué en place à chaque fichier temporaire, et un limiteur lié entre les pistes les baisse toutes d'un même gain là où leur somme dépasse encore la même limite (le gain varie progressivement sur 5 ms de chaque côté d'un pic), pour que le mixage reste la somme des pistes ;
  - le gain commun qui reste, `target_lufs - I` de cette somme, est petit, et toujours ramené si besoin pour que le true peak reste sous `true_peak_db` ; le fichier de montage dit alors que le volume visé n'est pas atteint.
- L'écriture du M3 coupe les fichiers temporaires limités (les voix au format de leur brut, le film à celui du film brut) et applique le gain restant à chaque piste, donc au mixage (`write_edit(..., gain_db=…)`). Le gain du fichier de montage est le total appliqué aux voix traitées : `g` + rattrapage + reste.
- Réglages `[sound]` : `enabled = true`, `denoise = true`, `filters` (ci-dessus), `target_lufs = -16.0`, `true_peak_db = -1.0`.

### Le fichier de montage

Une nouvelle section `### Sound` :
- la chaîne (`DeepFilterNet 3 + filters` ou `filters only`, ou `Not processed` si `enabled = false`), le gain du film et le gain commun appliqués ;
- un tableau par piste écrite et pour le mixage : LUFS et true peak avant (le brut) et après (le fichier écrit).

### Disque et temps

- La place vérifiée compte aussi les fichiers temporaires du son.
- Progression : `Processing the sound of <voix>… (the DeepFilterNet model is downloaded on first use)`, puis `Measuring the loudness…` et `Levelling the tracks…`.

## Laissé au constructeur

- Le découpage en modules (par exemple `sound/denoise.py`, `sound/filters.py`, `sound/loudness.py`), du moment que le débruiteur est derrière un protocole qu'un test peut remplacer par un faux.
- Le détail du fondu entre tranches de DeepFilterNet.
- Comment lire le true peak dans la sortie d'ffmpeg.

## Vérification

- Tests rapides avec un faux débruiteur (ffmpeg permis).
- Test lent sur `samples/pedit` : la chaîne complète, mixage à -16 ± 0,5 LUFS et true peak ≤ -1 dBTP ; la différence moyenne d'équilibre avec Auphonic ≤ 2,5 dB.
- **Écoute par Julien**, pistes et mixage contre `out/m4-preview/pedit-auphonic-same-volume.wav`, puis réglage de `filters` et note des valeurs retenues dans « Réglages validés » de `CLAUDE.md`.
