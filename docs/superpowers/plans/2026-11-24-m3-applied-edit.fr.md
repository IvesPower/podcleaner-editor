# M3 : montage appliqué, plan de mise en œuvre

**Français** · [English](2026-11-24-m3-applied-edit.md)

> **Pour les agents :** SOUS-SKILL REQUIS : utiliser superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans pour mettre en œuvre ce plan tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`) pour le suivi.

**Objectif :** `pedit run` sans `--dry-run` écrit l'audio monté.
- Chaque voix passe par une porte réglée comme la Strip Silence de Julien, et toutes les pistes sont coupées aux mêmes échantillons, avec un fondu croisé à chaque raccord.
- Il écrit aussi un mixage stéréo qui porte les marqueurs, et un fichier MIDI qui ne contient que les marqueurs.
- Le fichier de montage a des timecodes « Final » qui tombent exactement sur cet audio.

**Architecture :** l'analyse du M2 ne change pas. Elle calcule en plus, pour chaque voix, les passages où la porte est ouverte (`analysis/gate.py`), à partir des niveaux qu'elle a déjà. L'écriture forme un nouveau paquet, `render/` :
- `splice.py` traduit la carte des coupes en un plan de morceaux en échantillons, avec la longueur de chaque fondu (fonction pure) ;
- `gain.py` donne le gain de la porte sur un bloc d'échantillons ;
- `writer.py` fait un seul passage en flux avec `soundfile`, bloc par bloc, qui écrit toutes les pistes et le mixage sous des noms temporaires, puis les renomme ;
- `markers.py` écrit le fichier MIDI et les blocs `cue ` / `labl` du WAV.

`pipeline.run` relie le tout, et la CLI lève son refus du mode sans `--dry-run`.

**Outils :** ceux du M2. `soundfile` est déjà une dépendance, et le MIDI est écrit à la main : aucune nouvelle dépendance.

**Spec :** [conception du M3](../specs/2026-11-24-m3-applied-edit-design.fr.md) (approuvée par Julien le 24 nov. 2026) · [`docs/spec.fr.md`](../../spec.fr.md) (fait foi) · feuille de route : [`2026-11-05-roadmap.fr.md`](2026-11-05-roadmap.fr.md)

## Contraintes globales

- Les contraintes globales du M1 et du M2 restent valables :
  - plateformes, `pathlib`, UTF-8 ;
  - anglais partout, `HH:MM:SS.mmm` ;
  - titres de commit et de PR `type(portée): English / français` ;
  - documentation dans les deux langues.
- Une branche `feat/m3-applied-edit` et une PR pour le jalon, comme au M2.
- Jamais une piste pleine résolution entière en mémoire. On lit et on écrit par blocs de `_BLOCK_S = 5.0` secondes au plus, toutes pistes confondues.
- Toutes les pistes écrites ont exactement le même nombre d'échantillons : `n_out = n_total - échantillons coupés`, avec `n_total = round(episode.duration × fréquence)`.
- Les coupes sont celles de `AnalysisResult.cuts`, et rien d'autre. Une coupe s'écrit `[round(start × fr), round(end × fr))`, bornée à `[0, n_total]` ; une coupe vide est écartée.
- Fondu croisé à puissance constante, centré sur le raccord. Le gain de sortie vaut `cos(π/2 · x)` et celui d'entrée `sin(π/2 · x)`, avec `x = (j + 0,5) / (2h)` pour j = 0…2h-1. La demi-longueur vaut `h = min(round(fade_ms / 1000 × fr / 2), coupe // 2, morceau avant // 2, morceau après // 2)`.
- Porte : réglages par défaut -30 dB, 0,5 s, 10 ms d'attaque, 0,1 s de relâche. Elle est décidée au niveau sonore, avec le test de repisse si les pistes sont séparées. Elle n'est jamais appliquée à la piste film.
- Formats :
  - chaque piste est écrite avec le sous-type de son brut (`soundfile.info(path).subtype`) ;
  - le mixage est toujours en `FLOAT`, en stéréo ;
  - un fichier de plus de `0xFFFFFFFF` octets passe en `RF64`, et ses marqueurs WAV sont alors omis, avec un avertissement.
- Noms des sorties : `<nom>.<slug(voix)>.wav`, `<nom>.film.wav`, `<nom>.mix.wav`, `<nom>.markers.mid`.
- Aucun fichier à moitié écrit ne reste après une erreur ou un Ctrl+C.
- `--dry-run` n'écrit toujours aucun audio.
- Les tests rapides génèrent leurs WAV dans `tmp_path` avec `soundfile` ; ils n'utilisent ni modèle, ni réseau, ni `samples/`.

## Points à surveiller en revue

1. **Ctrl+C ou erreur au milieu de l'écriture** : aucun fichier `.tmp` ne reste. Les sorties d'un passage précédent restent intactes, puisqu'elles ne sont remplacées qu'au renommage final. Test à la tâche 4.
2. **Coupe au tout début ou à la toute fin de l'épisode** (un blanc avant la première phrase, ou après la dernière) : pas de fondu qui déborde des bornes, pas d'index négatif, la longueur reste exacte. Test à la tâche 3.
3. **Bruts en entiers** (PCM 16 ou 24 bits) : chaque piste garde son sous-type, le mixage est en float, et une somme qui dépasse 0 dBFS reste intacte dans le mixage. Test à la tâche 4.
4. **Pistes de longueurs différentes** (jusqu'à 2 s) : toutes les sorties ont `n_out` échantillons, et le fichier de montage dit ce qui a été laissé. Tests aux tâches 4 et 6.
5. **Noms de marqueurs avec accents, guillemets français ou `|`** : ils sont écrits en UTF-8 dans le MIDI et dans les `labl`, relus à l'identique, et coupés sans casser un caractère. Test à la tâche 5.

---

## Fichiers

```
src/podcleaner_editor/config.py            section [gate] (tâche 1)
src/podcleaner_editor/analysis/gate.py     gate_open (tâche 2)
src/podcleaner_editor/render/__init__.py
src/podcleaner_editor/render/splice.py     Piece, splice_plan (tâche 3)
src/podcleaner_editor/render/gain.py       gate_gain (tâche 2)
src/podcleaner_editor/render/writer.py     RenderTrack, write_edit (tâche 4)
src/podcleaner_editor/render/markers.py    Marker, write_midi, add_wav_markers, read_wav_markers (tâche 5)
src/podcleaner_editor/pipeline.py          portes dans analyze, écriture dans run (tâche 6)
src/podcleaner_editor/report/markdown.py   mode edit, Files, Tracks raccourcies (tâche 6)
src/podcleaner_editor/cli.py               run sans --dry-run (tâche 6)
tests/test_gate.py, test_splice.py, test_writer.py, test_render_markers.py
                                           + test_config, test_pipeline, test_markdown, test_cli
```

---

### Tâche 1 : réglages de la porte

**Fichiers :**
- Modifier : `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces :**
- Produit de nouveaux champs de `Settings`, dans une section `[gate]` placée juste après `[silences]` dans le modèle :

| Champ | Défaut | TOML | Commentaire du modèle |
| --- | --- | --- | --- |
| `gate_enabled: bool` | `True` | `[gate] enabled` | Silence each voice between its sentences, like Logic's Strip Silence. |
| `gate_threshold_db: float` | `-30.0` | `[gate] threshold_db` | A voice is heard above this level (dBFS). |
| `gate_min_silence_s: float` | `0.5` | `[gate] min_silence_s` | Shorter quiet moments stay open (seconds). |
| `gate_attack_s: float` | `0.010` | `[gate] attack_s` | The gate opens this long before the voice (seconds). |
| `gate_release_s: float` | `0.1` | `[gate] release_s` | The gate closes this long after the voice (seconds). |

- [ ] **Étape 1 : tests qui échouent**

```python
def test_gate_settings_read_from_toml(tmp_path):
    # [gate] threshold_db = -35, enabled = false → gate_threshold_db == -35.0, gate_enabled is False
def test_template_round_trips_gate_settings(tmp_path):
    # load_settings(file written by render_template(settings_values(Settings()))) == Settings()
```

- [ ] **Étape 2 :** `uv run pytest tests/test_config.py` → ÉCHEC.
- [ ] **Étape 3 :** ajouter les champs et les entrées de `_KEYS`.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(config): gate settings / réglages de la porte`.

---

### Tâche 2 : la porte (passages ouverts et gain)

**Fichiers :**
- Créer : `src/podcleaner_editor/analysis/gate.py`, `src/podcleaner_editor/render/__init__.py`, `src/podcleaner_editor/render/gain.py`, `tests/test_gate.py`

**Interfaces :**
- Utilise : `mask_to_intervals` (`analysis/activity.py`), `Interval`, `merge`, `Settings`.
- Produit :
  - `gate_open(levels: np.ndarray, other_levels: np.ndarray | None, hop_s: float, settings: Settings) -> list[Interval]`. Une trame est ouverte si `levels > gate_threshold_db` et, quand `other_levels` est donné, si `levels > other_levels - bleed_margin_db` (le test de `own_speech`, sur la longueur commune des deux tableaux). Les fermetures plus courtes que `gate_min_silence_s` sont rebouchées (`merge(…, gate_min_silence_s)`). Les passages ne sont **pas** élargis : c'est `gate_gain` qui applique l'attaque et la relâche.
  - `gate_gain(open_passages: list[Interval], first: int, count: int, rate: int, attack_s: float, release_s: float) -> np.ndarray` (float32, longueur `count`) : le gain des échantillons `[first, first + count)`.
    - Il vaut 1 dans un passage, et 0 loin de tout passage.
    - Sur les `attack_s` avant le début d'un passage, il monte linéairement de 0 à 1 ; sur les `release_s` après sa fin, il descend de 1 à 0.
    - Quand deux rampes se recouvrent, on prend le maximum.
    - Il ne regarde que les passages qui touchent le bloc : recherche par `bisect` dans la liste triée.

- [ ] **Étape 1 : tests qui échouent**

```python
def test_gate_opens_above_threshold():
    # hop 0.01, levels -60 partout sauf -20 sur les trames 100–199 → [I(1.0, 2.0)]
def test_gate_fills_short_closings():
    # ouvert 1.0–2.0 et 2.3–3.0 (fermeture 0,3 s < 0,5 s) → [I(1.0, 3.0)] ; fermeture 0,6 s → deux passages
def test_gate_ignores_bleed():
    # levels -25 (au-dessus du seuil) mais other_levels -10 (marge 10 dB) → [] ; other_levels=None → ouvert
def test_gate_gain_ramps():
    # passage [1.0, 2.0], rate 1000, attack 0.01, release 0.1 :
    # gain[990] ≈ 0.0, gain[995] ≈ 0.5, gain[1000:2000] == 1, gain[2050] ≈ 0.5, gain[2100:] == 0
def test_gate_gain_on_a_block_matches_the_whole():
    # gate_gain(p, 0, 3000, …)[1234:1734] == gate_gain(p, 1234, 500, …)
```

- [ ] **Étape 2 :** `uv run pytest tests/test_gate.py` → ÉCHEC.
- [ ] **Étape 3 :** écrire `gate_open` et `gate_gain`.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(gate): open passages and gain of the gate / passages ouverts et gain de la porte`.

---

### Tâche 3 : le plan des morceaux

**Fichiers :**
- Créer : `src/podcleaner_editor/render/splice.py`, `tests/test_splice.py`

**Interfaces :**
- Utilise : `CutMap`.
- Produit :
  - `@dataclass(frozen=True) class Piece: start: int; end: int; fade_in: int; fade_out: int`.
    - `[start, end)` est le morceau gardé, en échantillons de l'original.
    - `fade_in` et `fade_out` sont des demi-longueurs h, en échantillons.
    - Le morceau est lu sur `[start - fade_in, end + fade_out)`.
    - Ses `2 × fade_in` premiers échantillons montent, ses `2 × fade_out` derniers descendent.
    - Dans la sortie, il commence à la somme des longueurs `end - start` des morceaux précédents, moins `fade_in`.
  - `splice_plan(cuts: CutMap, n_total: int, rate: int, fade_ms: int) -> list[Piece]`. Les morceaux sont le complément des coupes dans `[0, n_total)`, en échantillons ; un morceau vide est écarté. Le `h` d'un raccord est donné dans les Contraintes globales et partagé par les deux morceaux. Le premier morceau a `fade_in = 0` et le dernier `fade_out = 0`. `sum(p.end - p.start) == n_out`.
  - `fade_curves(h: int) -> tuple[np.ndarray, np.ndarray]` : les gains d'entrée et de sortie (float32, longueur `2h`), dont les carrés font 1 en tout point.

- [ ] **Étape 1 : tests qui échouent**

```python
def test_no_cut_is_one_piece():                 # CutMap(()) , n_total 1000 → [Piece(0, 1000, 0, 0)]
def test_one_cut_two_pieces_with_shared_fade():
    # rate 1000, fade_ms 30, coupe [0.4, 0.6) → [Piece(0, 400, 0, 15), Piece(600, 1000, 15, 0)]
def test_fade_shortened_by_a_short_cut_or_piece():
    # coupe de 10 échantillons → h = 5 ; morceau de 8 échantillons entre deux coupes → h = 4 des deux côtés
def test_cut_at_start_and_end():
    # coupes [0, 0.2) et [0.9, 1.0) sur 1 s → un morceau Piece(200, 900, 0, 0), longueur 700
def test_output_length_is_exact():
    # 50 coupes au hasard (graine fixe) → sum(end - start) == n_total - échantillons coupés
def test_fade_curves_keep_power():
    # fade_curves(15) : fade_in² + fade_out² ≈ 1 partout ; fade_in croissant, fade_out décroissant
```

- [ ] **Étape 2 :** `uv run pytest tests/test_splice.py` → ÉCHEC.
- [ ] **Étape 3 :** écrire `Piece`, `splice_plan` et `fade_curves`.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(render): plan of the kept pieces and fades / plan des morceaux gardés et des fondus`.

---

### Tâche 4 : l'écriture en flux

**Fichiers :**
- Créer : `src/podcleaner_editor/render/writer.py`, `tests/test_writer.py`

**Interfaces :**
- Utilise : `Piece`, `splice_plan`, `fade_curves` (tâche 3) ; `gate_gain` (tâche 2) ; `EditorError`.
- Produit :
  - `@dataclass(frozen=True) class RenderTrack: source: Path; target: Path; gate: tuple[Interval, ...] | None` (`None` : pas de porte).
  - `write_edit(tracks: list[RenderTrack], pieces: list[Piece], n_total: int, mix_target: Path, settings: Settings) -> int`. La fonction écrit chaque piste et le mixage et renvoie `n_out`.
  - `check_renderable(sources: list[Path]) -> int`. Elle renvoie la fréquence commune. Sinon, `EditorError` :
    - `"The tracks do not share one sample rate ({liste}): convert them to the same rate first."` ;
    - `"{nom} has {n} channels: only mono or stereo tracks can be edited."`.
  - `estimate_bytes(sources: list[Path], n_out: int) -> int` et la vérification de place : si `shutil.disk_usage(dossier).free < 1,05 × estimation`, `EditorError(f"Not enough disk space in {dossier}: about {x:.1f} GB needed, {y:.1f} GB free.")`, levée avant d'ouvrir le moindre fichier.
- Comment ça marche :
  - **Lecture.** Chaque source est ouverte avec `soundfile.SoundFile`. On parcourt les morceaux ; chaque morceau est lu par blocs de `_BLOCK_S` au plus, avec `seek` puis `read(dtype="float32", always_2d=True)`.
  - **Porte.** Le gain `gate_gain` est appliqué en fonction de la position dans l'original.
  - **Fondus.** On garde en attente les `2 × fade_out` derniers échantillons déjà descendus d'un morceau. On y ajoute les `2 × fade_in` premiers, montés, du morceau suivant, puis on écrit le tout.
  - **Mixage.** Chaque bloc écrit sur les pistes est ajouté au même bloc du mixage. Une piste mono est copiée sur les deux canaux.
  - **Écriture sûre.** Tout s'écrit dans `<cible>.tmp` (`format="WAV"` ou `"RF64"`). Les renommages `os.replace` se font seulement à la fin, une fois tout écrit. Un `try` / `except BaseException` ferme et supprime les `.tmp`, puis relance l'exception.

- [ ] **Étape 1 : tests qui échouent** (WAV en rampe : l'échantillon i vaut `i / n` ; `gate=None` sauf mention)

```python
def test_tracks_cut_at_the_same_samples(tmp_path):
    # 2 pistes de 1 s à 1000 Hz, coupe [0.4, 0.6), fade_ms 0 → chaque sortie = rampe[0:400] + rampe[600:1000]
def test_crossfade_at_the_join(tmp_path):
    # fade_ms 30 → longueur 800 ; out[385:415] == rampe[385:415]·cos + rampe[585:615]·sin
def test_mix_is_the_sum(tmp_path):
    # voix mono 0.5 + film stéréo 0.75 → mix stéréo 1.25 sur les deux canaux, sous-type FLOAT
def test_integer_sources_keep_their_subtype(tmp_path):
    # PCM_24 → piste PCM_24 ; deux pistes à 0.9 → mix 1.8, non écrêté
def test_gate_applied_to_voice_only(tmp_path):
    # gate=(I(0.2, 0.3),) → hors [0.19, 0.4] la sortie vaut 0 ; la piste film sans porte reste intacte
def test_shorter_track_sets_the_length(tmp_path):
    # pistes de 1,0 s et 1,5 s, n_total = 1000 → les deux sorties ont 1000 - coupé échantillons
def test_error_mid_write_leaves_no_tmp_and_keeps_old_files(tmp_path, monkeypatch):
    # cibles existantes avec "old" ; un read qui lève KeyboardInterrupt au 2e bloc → aucun *.tmp, les cibles valent toujours "old"
def test_different_rates_refused(tmp_path):     # 44100 et 48000 → EditorError "do not share one sample rate"
def test_more_than_two_channels_refused(tmp_path):  # 6 canaux → EditorError "only mono or stereo"
def test_not_enough_space(tmp_path, monkeypatch):
    # disk_usage.free = 10 → EditorError "Not enough disk space", aucun fichier créé
```

- [ ] **Étape 2 :** `uv run pytest tests/test_writer.py` → ÉCHEC.
- [ ] **Étape 3 :** écrire `RenderTrack`, `check_renderable`, `estimate_bytes` et `write_edit`.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(render): stream the cut tracks and the mix to disk / écrire en flux les pistes coupées et le mixage`.

---

### Tâche 5 : les marqueurs (MIDI et WAV)

**Fichiers :**
- Créer : `src/podcleaner_editor/render/markers.py`, `tests/test_render_markers.py`

**Interfaces :**
- Produit :
  - `@dataclass(frozen=True) class Marker: time_s: float; name: str`.
  - `marker_name(kind: str, reason: str) -> str`. Le nom vaut `f"{kind}: {reason}"`, coupé à `MAX_NAME = 120` caractères, `"…"` compris ; on coupe entre des caractères, jamais au milieu d'un octet UTF-8.
  - `write_midi(markers: list[Marker], path: Path) -> None` : fichier MIDI standard de type 0, division 960.
    - Il commence par le tempo `FF 51 03 07 A1 20` (120 bpm) au tick 0.
    - Chaque marqueur est un événement `FF 06 <longueur VLQ> <texte UTF-8>` au tick `round(time_s × 1920)`, avec des deltas en VLQ. Les marqueurs sont triés par temps.
    - Le fichier finit par `FF 2F 00`.
    - Écriture sûre : `.tmp` puis `os.replace`.
  - `add_wav_markers(path: Path, markers: list[Marker], rate: int) -> bool`. La fonction ajoute à la fin du fichier :
    - un bloc `cue `, avec un point par marqueur : identifiant `k + 1`, position et `sample offset` `round(time_s × rate)`, `data` ;
    - un bloc `LIST` de type `adtl`, avec un `labl` par marqueur (texte UTF-8 terminé par un zéro, avec un octet de remplissage si la longueur est impaire).

    Puis elle corrige la taille `RIFF` à l'octet 4 et renvoie `True`. Elle ne touche pas un fichier `RF64` et renvoie `False` (c'est la tâche 6 qui avertit).
  - `read_wav_markers(path: Path) -> list[tuple[int, str]]` (position en échantillons, nom), qui sert aux tests et aux tests lents.

- [ ] **Étape 1 : tests qui échouent**

```python
def test_midi_bytes(tmp_path):
    # [Marker(0.5, "A"), Marker(1.0, "B")] → MThd 0/1/960 ; tempo ; FF 06 "A" au tick 960 ; FF 06 "B" delta 960 ; FF 2F 00
def test_midi_vlq_for_long_times(tmp_path):   # Marker(7200.0, …) → delta 13 824 000 encodé en VLQ et relu à l'identique
def test_wav_markers_round_trip(tmp_path):
    # WAV float stéréo écrit par soundfile + add_wav_markers → read_wav_markers == [(22050, "Clip to add: …")]
    # et soundfile.read lit toujours le même audio
def test_unicode_names_round_trip(tmp_path):
    # 'Requested cut: Spoken instruction: "dis Claude, on coupe « ça » | là"' → identique dans le MIDI et dans le WAV
def test_marker_name_is_cut_cleanly():
    # raison de 300 caractères accentués → len == 120, finit par "…", encodable en UTF-8
```

- [ ] **Étape 2 :** `uv run pytest tests/test_render_markers.py` → ÉCHEC.
- [ ] **Étape 3 :** écrire `Marker`, `marker_name`, `write_midi`, `add_wav_markers` et `read_wav_markers`.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(render): markers in a MIDI file and in the mix WAV / marqueurs dans un fichier MIDI et dans le WAV du mixage`.

---

### Tâche 6 : chaîne complète, fichier de montage et CLI

**Fichiers :**
- Modifier : `src/podcleaner_editor/pipeline.py`, `src/podcleaner_editor/report/markdown.py`, `src/podcleaner_editor/cli.py`, `tests/test_pipeline.py`, `tests/test_markdown.py`, `tests/test_cli.py`

**Interfaces :**
- Utilise : tout ce qui précède.
- Produit :
  - **Dans `analyze`.** Quand `gate_enabled` est vrai, `analyze` calcule `gate_open` pour chaque voix, avec les niveaux de l'autre voix si les pistes sont séparées, `None` si elles sont mélangées. Le résultat va dans `AnalysisResult.gates: dict[str, tuple[Interval, ...]] | None` (clé : le label de la voix), qui vaut `None` quand la porte est coupée.
  - **`AnalysisResult.outputs: tuple[Path, ...] = ()`.** Ce sont les fichiers écrits, remplis par `run` ; `dry_run` vaut `False` en mode montage.
  - **`markers_of(result: AnalysisResult) -> list[Marker]`** (dans `pipeline.py`). La liste contient chaque événement, au temps `cuts.to_final(event.start)` et nommé `marker_name(str(event.type), event.reason)`. Elle contient aussi chaque « euh » signalé (`f.cut is None`), au temps `cuts.to_final(f.word.start)` et nommé `marker_name("Hesitation", f"{f.track}: {f.reason}")`. Tout est trié par temps.
  - **`file_slug(label: str) -> str`.** La fonction met en minuscules, retire les accents (NFKD), remplace toute suite de caractères autres que `[a-z0-9]` par `-` et retire les `-` des bords. Exemples : `"Julien + Franck"` → `"julien-franck"`, `"Élodie"` → `"elodie"`. Un slug vide devient `"voice"`. Si deux voix donnent le même slug, on ajoute `-1` et `-2`.
  - **`run(episode, settings, out_dir, *, dry_run: bool, progress=…) -> list[Path]`.** La fonction renvoie le fichier de montage, puis les fichiers audio et le MIDI. Sans `dry_run`, elle fait dans l'ordre :
    1. `check_renderable` avant l'analyse ;
    2. l'analyse ;
    3. `splice_plan`, la vérification de place, puis `write_edit` avec la progression `"Writing the edited tracks…"` ;
    4. `add_wav_markers` sur le mixage ; si elle renvoie `False` (RF64), la ligne `"⚠ The mix is over 4 GB (RF64): its markers are only in <nom>.markers.mid."` ;
    5. `write_midi` ;
    6. le fichier de montage, en dernier.
  - **Fichier de montage.** `mode: edit` quand `dry_run` est faux. Il a une nouvelle section `### Files`, placée après Duration : une ligne `- <nom de fichier>` par sortie, ou `"None: dry run, no audio written."`. La section Tracks ajoute une colonne `Left out at the end`, qui vaut `format_tc(durée de la piste - episode.duration)` si la différence dépasse 1 ms, et `—` sinon.
  - **CLI.** `run` sans `--dry-run` ne lève plus d'erreur. La commande affiche `Written: <chemin>` pour chaque fichier.

- [ ] **Étape 1 : tests qui échouent** (faux VAD et faux `Transcriber` comme au M2 ; WAV générés à 8 kHz)
  - `test_run_writes_every_output` : les pistes séparées donnent `ep.edit.md`, `ep.<a>.wav`, `ep.<b>.wav`, `ep.film.wav`, `ep.mix.wav` et `ep.markers.mid`. Toutes les pistes ont le même nombre d'échantillons, `round(cuts.final_duration(duration) × 8000)` à ±1 près par coupe. Le fichier de montage dit `mode: edit` et liste ces fichiers.
  - `test_markers_match_events_and_flagged_fillers` : un marqueur `CUT_REQUEST` et un « euh » signalé donnent 2 marqueurs, aux temps « Final » du fichier de montage, dans le MIDI comme dans le mixage.
  - `test_gate_follows_settings` : `gate_enabled=False` donne `result.gates is None`, et les pistes de voix ne sont pas mises à zéro.
  - `test_mixed_layout_outputs` : un seul fichier de voix (label `"A + B"`) donne `ep.a-b.wav`, `ep.film.wav` et `ep.mix.wav`.
  - `test_dry_run_writes_no_audio` : seuls `ep.edit.md` et `ep.words.json` sont écrits ; le fichier de montage dit `mode: dry run` et `None: dry run, no audio written.`.
  - `test_tracks_section_reports_left_out_end` : avec une piste film plus longue de 1,5 s, la colonne `Left out at the end` vaut `00:00:01.500` pour le film et `—` pour les autres.
  - `test_file_slug` : les exemples ci-dessus, plus le cas des doublons.
  - `test_cli_run_without_dry_run` (`test_cli.py`) : le code de sortie est 0 et le message dit `Written:` au moins quatre fois.
- [ ] **Étape 2 :** `uv run pytest` → ÉCHEC sur ces tests.
- [ ] **Étape 3 :** écrire `markers_of`, `file_slug`, les portes dans `analyze`, `run(dry_run=…)`, les sections du rapport et la CLI. Mettre à jour les tests du M1 et du M2 qui appellent `run` ou lisent la section Tracks.
- [ ] **Étape 4 :** `uv run pytest` → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(pipeline): write the edited tracks, the mix and the markers / écrire les pistes montées, le mixage et les marqueurs`.

---

### Tâche 7 : vérification sur l'enregistrement de test et documentation

**Fichiers :**
- Modifier : `tests/test_pipeline.py`, `docs/spec.md`, `docs/spec.fr.md`, `docs/superpowers/plans/2026-11-05-roadmap.md`, `docs/superpowers/plans/2026-11-05-roadmap.fr.md`, `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

- [ ] **Étape 1 : test lent** `test_pedit_edit_outputs` (sauté sans `samples/pedit`) :
  - `run` sans `dry_run` vers `tmp_path` écrit les six fichiers ;
  - les quatre WAV ont le même nombre d'échantillons, à 44 100 Hz, en `FLOAT` ;
  - la durée vaut la durée finale du fichier de montage, à 1 ms près ;
  - `read_wav_markers(mix)` a autant de marqueurs que le MIDI, et `len(markers_of(result))` aussi ;
  - la piste de Julien vaut exactement 0 entre deux de ses phrases (par exemple autour de la parole de Franck vers 48 s).
- [ ] **Étape 2 :** `uv run pytest -m slow` → SUCCÈS. Noter le temps d'écriture.
- [ ] **Étape 3 : écoute avec Julien.**
  - `uv run pedit run --voice samples/pedit/pedit-full-piste-1-julien.wav --voice samples/pedit/pedit-full-piste-2-franck.wav --film samples/pedit/pedit-full-piste-3-film.wav --out out/pedit`.
  - Julien importe les pistes dans Logic Pro et écoute les raccords et la porte : les rires sont-ils gardés, la repisse coupée, et y a-t-il des débuts de mots mangés ?
  - Il importe `pedit.markers.mid`, puis les marqueurs du mixage (« Importer les marqueurs du fichier audio »), et dit lequel des deux tombe juste.
  - On ajuste `gate_release_s`, `gate_threshold_db` et `fade_ms` si besoin, puis on note les valeurs retenues et le format de marqueurs qui marche dans le tableau « Réglages validés » de `CLAUDE.md`.
  - Ensuite, la même chose sur un épisode entier : on note le temps de traitement et la place prise sur le disque.
- [ ] **Étape 4 : documentation, dans les deux langues.**
  - Cahier des charges : la porte dans le tableau des fonctionnalités, et les noms de fichiers dans « Sorties produites ».
  - Feuille de route : la ligne M3 passe de « à écrire » à « fait », avec la porte.
  - README : `run` sans `--dry-run`, les fichiers écrits, l'import dans Logic.
  - Journal des versions : les entrées du M3.
  - `CLAUDE.md` : la ligne « Sorties » et la porte dans le tableau des décisions ; la phrase « l'audio monté arrive avec M3 » de la section Commandes est mise à jour.
- [ ] **Étape 5 :** `uv run pytest`, `uv run ruff check` et `uv run ruff format --check` → SUCCÈS.
- [ ] **Étape 6 :** commit `docs(m3): applied edit in the spec, roadmap, README and changelog / montage appliqué dans le cahier des charges, la feuille de route, le README et le journal`.
