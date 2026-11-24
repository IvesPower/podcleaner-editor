# M3 : montage appliqué, conception

**Français** · [English](2026-11-24-m3-applied-edit-design.md)

24 nov. 2026 · discuté avec Julien

## Intention

Jusqu'ici, `pedit run` ne produit que le fichier de montage (`--dry-run`). Avec M3, il écrit l'audio monté. Julien importe les pistes dans Logic Pro, écoute le montage d'un bout à l'autre, puis finit à la main : il ajoute des coupes et insère les extraits de film là où les marqueurs le disent.

Aujourd'hui, dans Logic, il fait lui-même ce travail répétitif :

1. **Strip Silence** sur chaque piste de voix (-30 dB, 0,5 s, 10 ms d'attaque) : il ne reste à chaque personne que sa voix, en silence numérique entre ses phrases. Plus de repisse de l'autre micro ni de souffle de fond.
2. **Édition / déplacer / shuffle gauche** sur toutes les pistes ensemble : les trous où tout le monde se tait se referment partout à la fois.
3. Il **joint les pistes** en une seule.

M3 automatise ces trois gestes, ajoute les coupes que l'analyse a déjà trouvées (« euh » isolés, consignes parlées) et pose des marqueurs pour la suite du travail.

**C'est réussi si** Julien glisse les pistes dans Logic et passe son temps à écouter et à finir, pas à réparer des coupes : aucun clic aux raccords, des pistes qui restent synchronisées jusqu'à la dernière seconde, et des marqueurs qui tombent au bon endroit.

## Objectifs

- Une piste par voix (ou la piste des voix mélangées) et la piste film, **coupées aux mêmes endroits, à l'échantillon près**.
- Sur chaque piste de voix, une **porte** réglée comme la Strip Silence de Julien.
- Un **fondu croisé** à chaque raccord.
- Un **mixage stéréo** (somme des pistes).
- Les **marqueurs** dans un fichier MIDI et dans le WAV du mixage.
- Un fichier de montage dont les timecodes « Final » correspondent exactement à l'audio écrit.

## Hors objectifs

- **Son studio** (débruitage, EQ, compression, normalisation à -16 LUFS / -1 dBTP) : c'est M4. Le mixage du M3 est une somme brute, sans normalisation.
- **Fichier Final Cut Pro XML** pour Logic, avec des régions qu'on peut rallonger pour annuler une coupe : écarté pour l'instant, trop incertain sans essai dans Logic (fondus et marqueurs mal documentés). À reconsidérer si les coupes ratées s'avèrent fréquentes.
- **Avis de Claude** : c'est M5.

## Anti-objectifs (ce qui rendrait le jalon raté même si tout « marche »)

- Des pistes qui se décalent les unes des autres, même d'un échantillon.
- Des timecodes « Final » qui ne tombent pas sur l'audio écrit.
- Des clics ou des coupes audibles aux raccords.
- Charger une piste de 2 h 10 en entier en mémoire.
- Une porte qui avale les rires et les réactions courtes.
- Un fichier à moitié écrit laissé dans le dossier de sortie après une erreur ou une interruption.

## Contraintes

- Les bruts de Julien sont en 44,1 kHz, float 32 bits, stéréo, y compris les pistes d'une seule voix. Un épisode de 2 h 10 pèse environ 2,3 Go par piste : tout se fait en flux, bloc par bloc.
- Il y a quelques centaines de coupes par épisode (environ 200 blancs et 150 « euh »).
- macOS et Windows ; chemins via `pathlib` ; tout fonctionne sans Claude.
- Toutes les analyses restent sur l'audio original, comme au M1 et au M2. M3 ne change aucune détection.
- `soundfile` (libsndfile) est déjà une dépendance.

## Approches envisagées

| Approche | Ce qu'elle donne | Écartée parce que |
| --- | --- | --- |
| **1. Passage en flux en Python avec `soundfile`** (retenue) | Coupes à l'échantillon près, porte et fondus calculés en numpy, toutes les pistes et le mixage écrits dans le même passage, mémoire bornée, facile à tester sur de petits tableaux | — |
| 2. Une commande ffmpeg par piste (`atrim` + `afade` + `concat` par morceau) | Pas de code audio à écrire | Avec des centaines de morceaux, ffmpeg garde en mémoire tout ce qui attend son tour et déborde sur 2 h 10 ; une erreur dans un graphe de 350 branches est illisible |
| 3. Liste de collage ffmpeg (`concat` avec `inpoint` / `outpoint`) | Rapide et simple | Pas de fondus : un clic possible à chaque raccord |
| 4. Fichier Final Cut Pro XML en plus des fichiers coupés | Coupes annulables dans Logic en étirant une région | Trop incertain : la documentation de Logic ne dit rien des fondus ni des marqueurs à l'import (voir Hors objectifs) |

Julien a choisi l'approche 1.

## Ce qui a été décidé

### Les sorties

Dans le dossier de l'épisode, à côté de `<nom>.edit.md` et `<nom>.words.json` :

| Fichier | Contenu |
| --- | --- |
| `<nom>.<voix>.wav` | Une piste par voix, avec la porte et coupée (`separate`), ou la piste des voix mélangées (`mixed`) |
| `<nom>.film.wav` | La piste film coupée, sans porte |
| `<nom>.mix.wav` | Le mixage stéréo, avec les marqueurs inscrits dedans |
| `<nom>.markers.mid` | Un fichier MIDI qui ne contient que les marqueurs |

`<voix>` est le prénom de la configuration, réduit à un nom de fichier sûr sur macOS et Windows (par exemple `julien`, `julien-franck` pour les voix mélangées). *Choix de Claude.*

Les fichiers sont écrits dans le **même format que les bruts** : même fréquence, même encodage (float 32 bits chez Julien), mêmes canaux. Le mixage est stéréo, dans l'encodage de la piste la plus précise. *Choix de Claude.*

`--dry-run` ne change pas : rapport et timecodes, aucun audio.

### La porte (comme la Strip Silence de Julien)

Sur chaque piste de voix, l'audio est ramené à zéro (silence numérique) là où la personne ne parle pas.

- Réglages par défaut, ceux de Julien dans Logic, dans une nouvelle section `[gate]` : `threshold_db = -30`, `min_silence_s = 0.5`, `attack_s = 0.010`, et `release_s = 0.1`. *La valeur de `release_s` est un choix de Claude : Julien n'a pas donné de « post release », à vérifier à l'écoute.* Une clé `enabled` (`true` par défaut) permet de couper la porte.
- **Décidée au niveau sonore, pas par la détection de parole**, pour garder les rires, les souffles audibles et les réactions courtes, comme Strip Silence.
- Une trame est « ouverte » si son niveau dépasse `threshold_db`. Avec des pistes séparées, elle doit aussi passer le test de repisse déjà utilisé par l'analyse : ce micro n'est pas plus bas que l'autre de plus de `bleed_margin_db`. Sinon, la voix de Franck dans le micro de Julien rouvrirait la porte de Julien. Avec des voix mélangées, seul le seuil compte.
- Les fermetures plus courtes que `min_silence_s` sont rebouchées : la porte reste ouverte entre deux syllabes ou deux mots.
- Chaque passage ouvert commence `attack_s` plus tôt, avec une montée du gain de 0 à 1 sur cette durée. Il finit `release_s` plus tard, avec une descente de 1 à 0. Il n'y a pas de clic à l'ouverture ni à la fermeture.
- Les niveaux viennent de l'analyse existante (trames de `level_hop_s` = 10 ms sur la copie 16 kHz). Les passages ouverts, en secondes, sont ensuite appliqués à l'audio pleine résolution.
- La porte s'applique sur l'audio original, avant les coupes. Elle ne change ni les détections ni les timecodes.
- **Les passages ouverts sont calculés par `analyze()`**, qui a déjà les niveaux en main, et gardés dans `AnalysisResult`. L'écriture n'a donc pas à décoder chaque piste une seconde fois pour ses niveaux. `--dry-run` les calcule aussi, sans rien écrire. Le fichier de montage ne les détaille pas. *Choix de Claude.*
- La piste film n'a pas de porte.

### Les coupes et les fondus

- Les coupes sont celles que l'analyse calcule déjà (`AnalysisResult.cuts` : blancs raccourcis, « euh » coupés, consignes retirées). Une seule liste, appliquée de la même façon à toutes les pistes.
- Les temps sont convertis en échantillons une fois, par `round(t × fréquence)`. Toutes les pistes ont la même fréquence (sinon erreur, voir plus bas), donc elles sont coupées aux mêmes échantillons.
- À chaque raccord, il y a un **fondu croisé à puissance constante** (sinus / cosinus) de `fade_ms` (30 ms par défaut), **centré sur le point de raccord**. La fin du morceau d'avant déborde de 15 ms dans la partie retirée en descendant, le début du morceau d'après commence 15 ms avant en montant, et les deux se superposent. **La durée finale reste exactement celle de la carte des coupes.**
- Si une coupe ou un morceau gardé est plus court que le fondu, le fondu est raccourci à cette longueur.
- **Pistes de longueurs différentes** (jusqu'à `max_duration_mismatch_s`, 2 s par défaut, acceptés au chargement) : toutes les pistes sont arrêtées à la plus courte (`Episode.duration`, convertie en échantillons). C'est déjà la durée sur laquelle portent l'analyse et la carte des coupes. La section Tracks du fichier de montage indique, pour chaque piste raccourcie, combien de secondes de fin ont été laissées. *Choix de Claude.*
- La porte, puis le fondu croisé, s'appliquent à chaque piste. Le mixage est la somme des pistes déjà coupées.

### Le mixage

- C'est la somme des pistes coupées : voix (ou voix mélangées) et film, chacune au gain 1. Une piste mono est mise au centre (copiée sur les deux canaux).
- Il n'y a pas de normalisation et pas de limiteur : en float 32 bits, une somme qui dépasse 0 dBFS n'écrête pas dans le fichier. M4 fera la normalisation. Si les bruts sont en entiers (16 ou 24 bits), le mixage est écrit en float 32 bits pour la même raison. *Choix de Claude.*

### Les marqueurs

- **Ce qui devient un marqueur** : tous les événements du fichier de montage (coupes demandées, extraits à ajouter, extraits de film, chevauchements), plus les « euh » signalés mais pas coupés. Ce sont justement les endroits où Julien voudra peut-être couper. *Proposé par Claude, pas contredit par Julien.*
- **Position** : le timecode « Final » du début de l'événement, le même que dans le fichier de montage.
- **Nom** : le type puis la raison, par exemple `Clip to add: Spoken instruction: "dis Claude, ajoute l'extrait…"`, coupé à une longueur raisonnable. *Choix de Claude.*
- **Fichier MIDI** : fichier MIDI standard de type 0, qui ne contient qu'un tempo fixe (120 bpm) et un événement « marqueur » (méta FF 06) par marqueur, à la bonne position en ticks. Il est écrit à la main, sans nouvelle dépendance. *Choix de Claude.*
- **WAV du mixage** : un bloc `cue ` et un bloc `LIST`/`adtl` avec un `labl` par marqueur, ajoutés après les données audio du mixage, quand il est encore le fichier `.tmp`, avant qu'il remplace l'ancien mixage ; laissés de côté, comme en RF64, s'ils faisaient passer le fichier au-delà de 4 Gio. Logic sait lire ces marqueurs (« Importer les marqueurs du fichier audio »).
- Quel format Logic lit le mieux, et si le fichier MIDI tombe bien au début du projet : c'est à vérifier dans Logic. La feuille de route le prévoit au M6. Julien pourra le dire dès le premier essai du M3.

### Le fichier de montage

- `mode: edit` au lieu de `dry run`.
- Une nouvelle section `### Files` liste les fichiers écrits.
- La section Duration donne la durée réelle des pistes écrites, qui doit être égale à la durée finale calculée.

### La CLI et l'écriture des fichiers

- `pedit run` sans `--dry-run` écrit tout. Le message « Writing the edited audio comes in a later version » disparaît.
- La progression affiche une ligne par étape, par exemple `Writing the edited tracks…`, puis le chemin de chaque fichier écrit.
- **Écriture sûre** : chaque fichier est écrit sous un nom temporaire dans le même dossier, puis renommé à la fin. Une erreur ou un Ctrl+C ne laisse aucun fichier à moitié écrit, et les fichiers temporaires sont supprimés. Les fichiers d'un passage précédent sont remplacés sans question, puisqu'on relance souvent le même épisode. *Choix de Claude.*
- **Place sur le disque** : avant d'écrire, le programme estime la taille des sorties et s'arrête tout de suite avec une `EditorError` s'il n'y a pas la place. Il ne s'arrête pas après dix minutes d'écriture. *Choix de Claude.*
- **Fréquences différentes** entre les pistes : `EditorError` en mode montage, puisqu'on ne peut ni les couper aux mêmes échantillons ni les mixer. Le `--dry-run` continue de les accepter. *Choix de Claude.*
- **Plus de 2 canaux** sur une piste : `EditorError` en mode montage, puisque le mixage ne sait pas où les placer. *Choix de Claude.*
- **Plus de 4 Go** pour un fichier (par exemple 2 h 10 en 96 kHz float stéréo) : le format WAV classique ne peut pas l'écrire. Le fichier est écrit en RF64, que Logic lit. Les marqueurs restent alors seulement dans le fichier MIDI, et un avertissement le dit. *Choix de Claude, cas qui ne concerne pas les bruts actuels de Julien.*

### Tests

- **Tests rapides** sur des WAV générés dans `tmp_path`, par exemple un signal en rampe où chaque échantillon a une valeur connue. On y vérifie :
  - que chaque piste est coupée aux mêmes échantillons et a la durée finale exacte ;
  - la forme des fondus croisés et leur raccourcissement ;
  - la porte : seuil, rebouchage des fermetures courtes, attaque et relâche, test de repisse ;
  - la somme du mixage et le passage mono → stéréo ;
  - les octets du fichier MIDI (relus par un petit lecteur de test) ;
  - les blocs `cue ` / `labl` relus dans le WAV, que `soundfile` doit toujours savoir lire ;
  - l'absence de fichiers temporaires après une erreur ;
  - le manque de place et les fréquences différentes.
- **Tests lents** sur `samples/pedit` (sautés sans les fichiers) : `run` sans `--dry-run` écrit les quatre fichiers attendus. Les durées sont égales à la durée finale, les pistes sont synchronisées (même nombre d'échantillons), et le mixage porte autant de marqueurs que le fichier MIDI.
- **Écoute avec Julien** sur l'enregistrement de test, puis sur un épisode entier : on vérifie les raccords, la porte (rires gardés, repisse coupée) et l'import dans Logic du MIDI et des marqueurs du WAV. On ajuste les valeurs par défaut et on les note dans le tableau « Réglages validés » de `CLAUDE.md`.

### Documents à mettre à jour (dans les deux langues)

- Le cahier des charges : la porte dans le tableau des fonctionnalités et dans « Sorties produites ».
- La feuille de route : la ligne M3.
- Le README et le journal des versions.
- `CLAUDE.md` : la porte et les sorties dans le tableau des décisions.

## Laissé au constructeur

- Le découpage en modules. Par exemple : `render/gate.py` (les passages ouverts), `render/splice.py` (le plan des morceaux et des fondus en échantillons), `render/writer.py` (le passage en flux), `render/markers.py` (MIDI et blocs WAV). Il peut aussi suivre un autre découpage, pourvu que le calcul du plan reste pur et testable sans fichier.
- La taille des blocs lus et écrits (de l'ordre de quelques secondes d'audio).
- Lire toutes les pistes ensemble, ou une piste à la fois plus un mixage accumulé. Au constructeur de choisir, du moment que la mémoire reste bornée et que l'écriture reste correcte.
- La longueur maximale du nom d'un marqueur.
