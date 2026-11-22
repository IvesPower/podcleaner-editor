# M2 : transcription et marqueurs, plan de mise en œuvre

**Français** · [English](2026-11-22-m2-transcription-markers.md)

> **Pour les agents :** SOUS-SKILL REQUIS : utiliser superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans pour mettre en œuvre ce plan tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`) pour le suivi.

**Objectif :** `pedit run … --dry-run` transcrit aussi les passages actifs de chaque voix (timestamps par mot), repère les marqueurs vocaux (« Claude ici on veut couper », « Claude ici on veut ajouter un extrait ») et les « euh », décide quels « euh » et quelles phrases de marqueur peuvent être coupés, et écrit tout cela dans le fichier de montage, avec des timecodes finaux qui tiennent déjà compte de ces coupes.

**Architecture :** la transcription est un module de bord (`analysis/transcribe.py` : mlx-whisper sur Apple Silicon, faster-whisper ailleurs, adapté du `transcribe.py` de podcleaner-clips) derrière un protocole `Transcriber`, pour tester la chaîne avec un faux. Tout ce qui suit est fait de fonctions pures sur des listes de `Word` et d'`Interval` (`detect/fillers.py`, `detect/markers.py`). Chaque voix n'est transcrite que sur sa propre parole (filtre de repisse du M1), et ses mots sont gardés en cache dans `<out>/<nom>.words.json` : un deuxième `--dry-run` avec d'autres réglages ne retranscrit pas. Les coupes des hésitations et des phrases de marqueur rejoignent celles des blancs dans une seule carte des coupes ; les blancs sont calculés une fois ces coupes retirées de l'activité, pour qu'un « euh » entre deux pauses laisse une seule pause courte, pas une longue.

**Outils :** ceux du M1, plus `mlx-whisper` (macOS arm64) / `faster-whisper` (ailleurs), modèle `large-v3-turbo`, et `rapidfuzz`.

**Spec :** [`docs/spec.fr.md`](../../spec.fr.md) (fait foi) · feuille de route : [`2026-11-05-roadmap.fr.md`](2026-11-05-roadmap.fr.md) · plan du M1 : [`2026-11-05-m1-foundations-analysis.fr.md`](2026-11-05-m1-foundations-analysis.fr.md)

## Contraintes globales

- Toutes les contraintes globales du M1 restent valables (plateformes, `pathlib`, UTF-8, anglais partout, `HH:MM:SS.mmm`, une branche et une PR par tâche, titres de commit et de PR `type(portée): English / français`, documentation dans les deux langues).
- On ne transcrit que les passages actifs, jamais la piste entière ; jamais l'audio pleine résolution en mémoire ; au plus une piste voix décodée en mémoire pendant la transcription.
- Sans Claude, tout fonctionne avec des règles fixes ; le M2 ne sollicite pas Claude.
- Règle d'un « euh » (choisie par Julien le 22 nov. 2026, « large ») : tout mot d'hésitation seul est coupé, sauf si un autre mot ou la parole de l'autre voix tombe dans sa fenêtre de coupe, ou un extrait de film, ou s'il dure plus de `filler_max_s` ; ceux-là sont signalés, jamais coupés. Claude (M5) pourra annuler une coupe.
- Voix mélangées : un « euh » n'est candidat à la coupe que si aucun autre mot transcrit ne chevauche la fenêtre de coupe (cahier des charges).
- Marqueurs vocaux : un événement `Requested cut` ou `Clip to add` dans les Timecodes, et la phrase elle-même est coupée de l'audio (choisi par Julien le 22 nov. 2026), à la même condition « aucune autre parole, pas de film ».
- Les coupes sont identiques sur toutes les pistes : toute coupe (blanc, « euh », marqueur) est bloquée par de la parole sur une autre piste.
- `--dry-run` n'écrit toujours aucun audio ; le cache des mots (JSON) est permis.
- Texte français permis dans le code et la configuration seulement pour la parole à reconnaître : les phrases des marqueurs, les mots d'hésitation et l'invite de Whisper.
- Les tests rapides ne chargent aucun modèle et n'utilisent pas le réseau ; les tests qui chargent Whisper sont marqués `slow` et sont sautés sans `samples/pedit`.
- Le téléchargement du modèle au premier passage (~1,6 Go depuis Hugging Face) est annoncé dans la ligne de progression.

## Points à surveiller en revue

1. **Whisper omet les « euh »** : il a tendance à écrire une parole propre. L'invite contient des hésitations (`"Euh, alors, euh… bon, hum, voilà."`) pour qu'il les écrive. Test à la tâche 2 (invite transmise aux deux moteurs) ; nombre vérifié sur l'enregistrement de test à la tâche 7.
2. **La repisse de l'autre voix transcrite sur le mauvais micro** : un marqueur ou un « euh » apparaîtrait deux fois, sur les deux pistes. Les mots dont le milieu tombe hors de la parole propre de la piste sont écartés. Tests aux tâches 2 et 7.
3. **Un « euh » entre deux pauses** : `pause de 0,7 s + euh + pause de 0,7 s` ne doit pas devenir un blanc de 1,4 s une fois le « euh » coupé. Les blancs sont calculés avec les coupes de parole retirées de l'activité. Test à la tâche 7.
4. **Premier passage sans réseau, ou modèle qui ne se charge pas** : message clair (`Error: Could not load the Whisper model large-v3-turbo: …`), code de sortie 2, pas de trace Python. Test à la tâche 2.
5. **Cache des mots périmé ou abîmé** : un WAV modifié, d'autres réglages de transcription ou un JSON tronqué doivent mener à une nouvelle transcription, jamais à la réutilisation de mauvais mots ni à un plantage. Tests à la tâche 3.

---

## Fichiers

```
src/podcleaner_editor/config.py                 nouveaux réglages (tâche 1)
src/podcleaner_editor/timeline.py               subtract (tâche 4)
src/podcleaner_editor/analysis/words.py         Word, normalize, speech_passages, keep_own_words
src/podcleaner_editor/analysis/transcribe.py    Transcriber, moteurs, make_transcriber, transcribe_passages
src/podcleaner_editor/analysis/words_cache.py   cache_key, load_words, save_words
src/podcleaner_editor/detect/cuts.py            cut_window, snap_to_quiet, blocking_reason
src/podcleaner_editor/detect/fillers.py         Filler, is_filler, find_fillers
src/podcleaner_editor/detect/markers.py         Marker, find_markers
src/podcleaner_editor/report/markdown.py        nouvelles sections
src/podcleaner_editor/pipeline.py               étape de transcription, coupes de parole
tests/test_words.py, test_transcribe.py, test_words_cache.py, test_cuts.py,
tests/test_fillers.py, test_markers.py          + test_config, test_timeline, test_markdown, test_pipeline
```

---

### Tâche 1 : réglages et dépendances

**Fichiers :**
- Modifier : `pyproject.toml`, `uv.lock`, `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces :**
- Produit de nouveaux champs de `Settings` (section et clé TOML entre crochets, ordre du modèle comme listé, après `[film]` et avant `[overlaps]`) :

| Champ | Défaut | TOML | Commentaire du modèle |
| --- | --- | --- | --- |
| `whisper_model: str` | `"large-v3-turbo"` | `[transcription] model` | Whisper model (mlx-community name on Apple silicon). |
| `transcription_language: str` | `"fr"` | `[transcription] language` | Language spoken in the episode. |
| `transcription_prompt: str` | `"Euh, alors, euh… bon, hum, voilà."` | `[transcription] prompt` | Example text that makes Whisper write the hesitations. |
| `passage_gap_s: float` | `1.0` | `[transcription] passage_gap_s` | Speech closer than this is transcribed in one passage (seconds). |
| `passage_pad_s: float` | `0.2` | `[transcription] passage_pad_s` | Margin added around each passage (seconds). |
| `filler_words: tuple[str, ...]` | `("euh", "heu", "euhm", "hum", "hm")` | `[hesitations] words` | Words counted as hesitations. |
| `filler_pad_s: float` | `0.05` | `[hesitations] pad_s` | Margin cut around a hesitation (seconds). |
| `filler_max_s: float` | `1.5` | `[hesitations] max_s` | Longer hesitations are flagged, not cut (seconds). |
| `filler_snap_s: float` | `0.08` | `[hesitations] snap_s` | How far a cut edge may move to the quietest point (seconds). |
| `marker_cut_phrase: str` | `"claude ici on veut couper"` | `[markers] cut` | Phrase that asks for a cut. |
| `marker_clip_phrase: str` | `"claude ici on veut ajouter un extrait"` | `[markers] clip` | Phrase that asks for a clip to be added. |
| `marker_min_score: float` | `85.0` | `[markers] min_score` | Lowest similarity (0 to 100) for a heard phrase to count. |
| `marker_pad_s: float` | `0.1` | `[markers] pad_s` | Margin cut around a marker phrase (seconds). |

- [ ] **Étape 1 :** dépendances : `"mlx-whisper ; sys_platform == 'darwin' and platform_machine == 'arm64'"`, `"faster-whisper ; sys_platform != 'darwin' or platform_machine != 'arm64'"`, `"rapidfuzz"` ; `uv lock`.
- [ ] **Étape 2 : tests qui échouent**

```python
def test_filler_words_read_from_toml(tmp_path):
    # [hesitations] words = ["euh", "bah"] → settings.filler_words == ("euh", "bah")
def test_filler_words_must_be_non_empty_strings(tmp_path):
    # words = [] → EditorError; words = ["euh", 3] → EditorError, message names "[hesitations] words"
def test_template_round_trips_new_settings(tmp_path):
    # load_settings(file written by render_template(settings_values(Settings()))) == Settings()
```

- [ ] **Étape 3 :** `uv run pytest tests/test_config.py` → ÉCHEC.
- [ ] **Étape 4 :** ajouter les champs et les entrées de `_KEYS` ; dans `_convert`, un défaut `tuple` autre que `speakers` prend une liste non vide de textes non vides (`"{label} must list words, such as [\"euh\", \"heu\"]"`).
- [ ] **Étape 5 :** `uv run pytest` → SUCCÈS (y compris les tests du M1 : l'assertion sur `_KEYS` tient).
- [ ] **Étape 6 :** commit `feat(config): transcription, hesitation and marker settings / réglages de transcription, d'hésitations et de marqueurs`.

---

### Tâche 2 : mots, passages et transcription

**Fichiers :**
- Créer : `src/podcleaner_editor/analysis/words.py`, `src/podcleaner_editor/analysis/transcribe.py`, `tests/test_words.py`, `tests/test_transcribe.py`

**Interfaces :**
- Utilise : `Interval`, `merge`, `Settings`, `EditorError`, `ANALYSIS_RATE`.
- Produit :
  - `words.py` : `@dataclass(frozen=True) class Word: text: str; start: float; end: float` (secondes sur l'audio original) avec la propriété `span -> Interval` ; `normalize(text: str) -> str` (minuscules, accents retirés par NFKD, tout caractère non alphanumérique → espace, espaces regroupés, bords retirés) ; `speech_passages(speech: list[Interval], total: float, gap_s: float, pad_s: float) -> list[Interval]` (fusion avec `gap_s`, élargissement de `pad_s`, borné à `[0, total]`, nouvelle fusion) ; `keep_own_words(words: list[Word], own: list[Interval], tolerance: float) -> list[Word]` (garde un mot dont le milieu tombe dans un intervalle de `own` élargi de `tolerance`).
  - `transcribe.py` : `class Transcriber(Protocol)` : `name: str` ; `words(self, audio: np.ndarray, offset: float) -> list[Word]` (audio mono 16 kHz, temps décalés de `offset`, triés, textes vides écartés). `make_transcriber(settings: Settings) -> Transcriber` (mlx sur darwin/arm64, faster-whisper sinon ; `name` du genre `"mlx-whisper large-v3-turbo"` ; le modèle se charge au premier appel). Les deux moteurs passent `language=settings.transcription_language`, `initial_prompt=settings.transcription_prompt`, `word_timestamps=True`, `condition_on_previous_text=False` ; dépôt mlx `mlx-community/whisper-<modèle>` sauf si le nom contient un `/` ; faster-whisper `compute_type="int8"`. Toute exception à l'import ou au chargement du modèle → `EditorError(f"Could not load the Whisper model {model}: {exc}")`. `transcribe_passages(samples: np.ndarray, passages: list[Interval], transcriber: Transcriber) -> list[Word]` (un appel par passage avec `offset = passage.start`, résultats réunis et triés). `@dataclass(frozen=True) class TranscriptionInfo: backend: str; speech_s: float; cached_tracks: int`.

- [ ] **Étape 1 : tests qui échouent**

```python
def test_normalize_strips_case_accents_and_punctuation():
    assert normalize("Claude, ici… On VEUT couper !") == "claude ici on veut couper"
    assert normalize("Été") == "ete" and normalize("aujourd'hui") == "aujourd hui"

def test_speech_passages_merge_pad_and_clamp():
    assert speech_passages([I(0.1, 2), I(2.5, 4), I(8, 9.9)], total=10, gap_s=1.0, pad_s=0.2) \
        == [I(0, 4.2), I(7.8, 10)]

def test_keep_own_words_drops_bleed():
    words = [Word("oui", 1.0, 1.2), Word("non", 5.0, 5.2)]
    assert keep_own_words(words, [I(0.5, 2)], tolerance=0.2) == [words[0]]

def test_transcribe_passages_shifts_times(): ...   # faux moteur, 2 passages → décalages 3,0 et 10,0, mots triés
def test_mlx_backend_passes_prompt_and_language(monkeypatch):
    # faux module `mlx_whisper` dans sys.modules qui note les arguments :
    # initial_prompt == Settings().transcription_prompt, language == "fr", word_timestamps is True
def test_faster_whisper_backend_passes_prompt_and_language(monkeypatch): ...   # idem, faux faster_whisper.WhisperModel
def test_model_load_failure_is_an_editor_error(monkeypatch):
    # faux module dont transcribe lève OSError("offline") →
    # EditorError("Could not load the Whisper model large-v3-turbo: offline")
```

- [ ] **Étape 2 : test lent** `test_transcribes_french_speech` (sauté sans `samples/pedit`) : les 15 premières secondes de `pedit-full-piste-1-julien.wav` → au moins 10 mots, tous avec `0 <= start <= end <= 15`.
- [ ] **Étapes 3 à 5 :** ÉCHEC → mise en œuvre → `uv run pytest` et `uv run pytest -m slow tests/test_transcribe.py` → SUCCÈS.
- [ ] **Étape 6 :** commit `feat(transcribe): word-level transcription of active passages / transcription au mot des passages actifs`.

---

### Tâche 3 : cache des mots

**Fichiers :**
- Créer : `src/podcleaner_editor/analysis/words_cache.py`, `tests/test_words_cache.py`

**Interfaces :**
- Utilise : `Word`, `Interval`, `Settings`.
- Produit : `cache_key(path: Path, passages: list[Interval], settings: Settings) -> dict` (nom du fichier, taille, `st_mtime_ns`, `whisper_model`, `transcription_language`, `transcription_prompt`, et les passages arrondis à la milliseconde) ; `load_words(cache_path: Path, label: str, key: dict) -> list[Word] | None` (`None` si le fichier manque, est illisible, n'a pas la forme JSON attendue, ou si sa clé pour `label` diffère) ; `save_words(cache_path: Path, label: str, key: dict, words: list[Word]) -> None` (garde les entrées des autres pistes, écrit en UTF-8 dans un fichier temporaire puis `os.replace`). Forme du fichier : `{"version": 1, "tracks": {label: {"key": {...}, "words": [[texte, début, fin], ...]}}}`.

- [ ] **Étape 1 : tests qui échouent** : `test_round_trip` ; `test_two_tracks_in_one_file` ; `test_changed_file_misses` (WAV réécrit → `None`) ; `test_changed_prompt_misses` ; `test_changed_passages_misses` ; `test_truncated_json_misses` (fichier contenant `{"version": 1, "tra` → `None`, aucune exception) ; `test_wrong_shape_misses` (`{"version": 1, "tracks": []}` → `None`).
- [ ] **Étapes 2 à 4 :** ÉCHEC → mise en œuvre → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(transcribe): cache the words of each track / garder en cache les mots de chaque piste`.

---

### Tâche 4 : fenêtres de coupe et hésitations

**Fichiers :**
- Créer : `src/podcleaner_editor/detect/cuts.py`, `src/podcleaner_editor/detect/fillers.py`, `tests/test_cuts.py`, `tests/test_fillers.py`
- Modifier : `src/podcleaner_editor/timeline.py`, `tests/test_timeline.py`

**Interfaces :**
- Utilise : `Word`, `normalize`, `Interval`, `merge`, `intersect`, `invert`, `Settings`.
- Produit :
  - `timeline.subtract(a: list[Interval], b: list[Interval]) -> list[Interval]` : les moments de `a` que `b` ne couvre pas.
  - `cuts.py` (partagé avec la tâche 5) :
    - `cut_window(span: Interval, prev_end: float | None, next_start: float | None, pad: float) -> Interval` : `span` élargi de `pad`, jamais au-delà de la fin du mot précédent ni du début du suivant sur la même piste.
    - `snap_to_quiet(window: Interval, span: Interval, levels: np.ndarray, hop_s: float, snap_s: float, bounds: Interval) -> Interval` : chaque bord va sur la trame la plus calme à moins de `snap_s` de lui, en restant hors de `span` et dans `bounds` (les limites des voisins).
    - `blocking_reason(window: Interval, other_speech: list[Interval], film: list[Interval]) -> str | None` : `"Other speech at the same time"` si `window` croise `other_speech`, sinon `"During a film clip"` s'il croise `film`, sinon `None`.
  - `fillers.py` :
    - `@dataclass(frozen=True) class Filler: word: Word; track: str; context: str; cut: Interval | None; reason: str` (`cut` vaut `None` pour un « euh » signalé ; `reason` vaut `"Isolated hesitation"` quand il est coupé).
    - `is_filler(text: str, words: tuple[str, ...]) -> bool` : `normalize(text)` est un seul mot et, lettres répétées réduites (`euuuh` → `euh`), égale l'un des `words` réduits de même.
    - `find_fillers(words: dict[str, list[Word]], other_speech: dict[str, list[Interval]], film: list[Interval], levels: dict[str, np.ndarray], settings: Settings) -> list[Filler]`, par étiquette de piste, trié par temps. Pour chaque mot d'hésitation : s'il dure plus de `filler_max_s` → signalé `"Too long to be sure it is a hesitation"` ; si le mot précédent sur la même piste finit après son début, ou si le suivant commence avant sa fin → signalé `"Other speech at the same time"` ; sinon fenêtre = `snap_to_quiet(cut_window(...))`, et `blocking_reason(window, other_speech[track], film)` le signale, ou il est coupé. `context` : jusqu'à 4 mots avant et 4 après, le « euh » entre crochets (`"alors [euh] on a vu"`).

- [ ] **Étape 1 : tests qui échouent**

```python
def test_subtract():
    assert subtract([I(0, 10)], [I(2, 3), I(5, 6)]) == [I(0, 2), I(3, 5), I(6, 10)]

def test_cut_window_stops_at_neighbours():
    assert cut_window(I(5.0, 5.4), prev_end=4.98, next_start=5.6, pad=0.05) == I(4.98, 5.45)

def test_snap_moves_edges_to_quiet_frames(): ...   # niveaux avec un creux 0,06 s avant le début de la fenêtre → le début s'y pose
def test_snap_never_enters_the_word(): ...
def test_blocking_reason_order(): ...               # autre parole et film à la fois → "Other speech at the same time"

def test_isolated_euh_is_cut():
    words = {"Julien": [Word("alors", 4.0, 4.6), Word("euh", 5.0, 5.4), Word("on", 5.8, 6.0)]}
    [f] = find_fillers(words, {"Julien": []}, [], {"Julien": quiet_levels}, SETTINGS)
    assert f.cut is not None and f.cut.start <= 5.0 and f.cut.end >= 5.4 and f.reason == "Isolated hesitation"
    assert f.context == "alors [euh] on"

def test_variants_count_as_fillers():
    assert is_filler("Euuuh…", SETTINGS.filler_words) and is_filler("Hum,", SETTINGS.filler_words)
    assert not is_filler("heureux", SETTINGS.filler_words) and not is_filler("euh bon", SETTINGS.filler_words)

def test_euh_under_the_other_voice_is_flagged(): ...      # other_speech couvre 5,2–5,3 → cut None, "Other speech at the same time"
def test_euh_overlapping_a_word_on_the_same_track_is_flagged(): ...   # voix mélangées : le mot suivant commence à 5,3
def test_euh_during_film_clip_is_flagged(): ...           # "During a film clip"
def test_long_euh_is_flagged(): ...                       # 2,0 s → "Too long to be sure it is a hesitation"
```

- [ ] **Étapes 2 à 4 :** ÉCHEC → mise en œuvre → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(hesitations): find the "euh"s and decide which can be cut / repérer les « euh » et choisir ceux à couper`.

---

### Tâche 5 : marqueurs vocaux

**Fichiers :**
- Créer : `src/podcleaner_editor/detect/markers.py`, `tests/test_markers.py`

**Interfaces :**
- Utilise : `Word`, `normalize`, `cut_window`, `snap_to_quiet`, `blocking_reason` (tâche 4), `Event`, `EventType`, `Settings`, `rapidfuzz.fuzz.ratio`.
- Produit : `@dataclass(frozen=True) class Marker: event: Event; cut: Interval | None` ; `find_markers(words: list[Word], track: str, other_speech: list[Interval], film: list[Interval], levels: np.ndarray, settings: Settings) -> list[Marker]`, trié par temps.
  Règle : les mots de la piste deviennent des jetons (`normalize`, découpe ; chaque jeton garde son mot). Pour chaque phrase (`marker_cut_phrase` → `CUT_REQUEST`, `marker_clip_phrase` → `CLIP_TO_ADD`) de `n` jetons, toute fenêtre de `n - 1`, `n` ou `n + 1` jetons consécutifs est candidate si `fuzz.ratio(texte de la fenêtre, phrase) >= marker_min_score` **et** `fuzz.ratio(dernier jeton de la fenêtre, dernier jeton de la phrase) >= 70` (le mot qui distingue : « couper », « extrait »). Les candidates sont gardées par score, la meilleure d'abord, en sautant celles qui partagent un mot avec une déjà gardée. Événement : `start`/`end` = premier et dernier mot de la fenêtre, `track`, raison `'Spoken marker "<mots entendus, tels que transcrits>" (score <entier>)'`. Coupe : comme pour un « euh », avec `marker_pad_s` ; si `blocking_reason` renvoie une raison, `cut = None` et la raison de l'événement se termine par `"; phrase kept: <raison>"`.

- [ ] **Étape 1 : tests qui échouent**

```python
def test_cut_marker_with_punctuation():
    words = _words("bon Claude, ici on veut couper ! alors")
    [m] = find_markers(words, "Julien", [], [], quiet_levels, SETTINGS)
    assert m.event.type == EventType.CUT_REQUEST and m.event.track == "Julien"
    assert (m.event.start, m.event.end) == (words[1].start, words[5].end) and m.cut is not None

def test_clip_marker_is_not_also_a_cut(): ...             # « claude ici on veut ajouter un extrait » → un seul CLIP_TO_ADD
def test_misheard_word_still_matches(): ...                # « clode ici on veut couper » → CUT_REQUEST
def test_dropped_word_still_matches(): ...                 # « claude on veut couper » → CUT_REQUEST
def test_sentence_that_starts_like_a_marker_is_ignored():  # « claude ici on veut du café » → []
def test_two_markers_in_a_row(): ...                       # les deux phrases à la suite → 2 marqueurs
def test_marker_under_other_speech_is_kept_in_audio(): ... # cut None, raison finit par "; phrase kept: Other speech at the same time"
```

- [ ] **Étapes 2 à 4 :** ÉCHEC → mise en œuvre → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(markers): find the spoken markers / repérer les marqueurs vocaux`.

---

### Tâche 6 : fichier de montage

**Fichiers :**
- Modifier : `src/podcleaner_editor/report/markdown.py`, `tests/test_markdown.py`

**Interfaces :**
- Utilise : `Filler`, `TranscriptionInfo`, `CutMap`, `merge`.
- Produit : `AnalysisResult` gagne `fillers: tuple[Filler, ...] = ()`, `marker_cuts: tuple[Interval, ...] = ()`, `transcription: TranscriptionInfo | None = None`, et la propriété `cuts -> CutMap` = `CutMap(tuple(merge([*silence_cuts.cuts, *coupes des « euh », *marker_cuts])))`. La colonne Final des Timecodes et les durées utilisent `cuts`. Nouvelle forme du Rapport :

```
## Report
### Duration      Final duration: 01:58:12.400 (original: 02:10:03.000), 00:11:50.600 removed.
### Tracks        (inchangé)
### Silences      214 silences shortened, 00:09:01.200 removed.
### Hesitations   153 hesitations removed (00:01:02.300), 12 flagged:
                  | Original | Final | Track | Context | Reason |   (signalés seulement)
### Markers       3 spoken markers: 2 requested cuts, 1 clip to add; 3 phrases removed (00:00:05.100).
### Overlaps      (inchangé)
### Transcription mlx-whisper large-v3-turbo · 00:58:40.000 of speech transcribed · 1 of 2 tracks from the cache.
### Claude's opinions (inchangé)
```

Sans transcription (`transcription is None`), Hesitations et Markers disent `Not available: the episode was not transcribed.` et la section Transcription dit `None.` ; sans « euh » signalé, pas de tableau.

- [ ] **Étape 1 : tests qui échouent** : `test_final_column_counts_filler_and_marker_cuts` (coupe de blanc 10–12 s, coupe de « euh » 20–20,5 s, événement à 30 s → Final `00:00:27.500`) ; `test_hesitations_section_lists_flagged_only` ; `test_markers_section_counts_by_type` ; `test_transcription_section` ; `test_without_transcription_sections_say_not_available` ; `test_duration_section`. Mettre à jour les tests du M1 qui lisent l'ancienne phrase « Final duration » de la section Silences.
- [ ] **Étapes 2 à 4 :** ÉCHEC → mise en œuvre → SUCCÈS.
- [ ] **Étape 5 :** commit `feat(report): hesitations, markers and transcription in the edit file / hésitations, marqueurs et transcription dans le fichier de montage`.

---

### Tâche 7 : chaîne d'analyse, CLI et vérification sur l'enregistrement de test

**Fichiers :**
- Modifier : `src/podcleaner_editor/pipeline.py`, `tests/test_pipeline.py`, `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

**Interfaces :**
- Utilise : tout ce qui précède.
- Produit : `analyze(episode, settings, *, decode=None, vad=None, transcriber: Transcriber | None = None, cache_path: Path | None = None, progress=…) -> AnalysisResult` (`transcriber` vaut par défaut `make_transcriber(settings)`, créé seulement si le cache manque). `run(...)` passe `cache_path = out_dir / f"{episode.name}.words.json"`. Aucune nouvelle option de la CLI.
  Après les étapes du M1 (parole propre, extraits de film), et avant les blancs :
  1. Pour chaque voix, dans l'ordre, progression `"Transcribing <label>…"` (le premier manque du cache ajoute ` (the first run downloads the Whisper model, about 1.6 GB)`) : passages = `speech_passages(own[i], episode.duration, passage_gap_s, passage_pad_s)` ; `load_words`, sinon nouveau décodage de cette piste, `transcribe_passages`, `keep_own_words(…, own[i], passage_pad_s)` (pistes séparées seulement), `save_words`, libération des échantillons.
  2. `other_speech[label]` : pistes séparées, les mots de l'autre voix unis à sa parole propre ; voix mélangées, `[]`.
  3. `find_fillers`, puis `find_markers` par voix ; les événements des marqueurs rejoignent les événements.
  4. Coupes de parole = les « euh » et marqueurs coupés. Chaque liste de parole propre et de sons forts de chaque voix passée à `find_silence_cuts` devient `subtract(liste, coupes_de_parole)`.
  5. `AnalysisResult(..., fillers=…, marker_cuts=…, transcription=TranscriptionInfo(nom du moteur ou "cache", somme des durées des passages, pistes lues dans le cache))`.

- [ ] **Étape 1 : tests qui échouent** (faux VAD comme au M1, faux `Transcriber` qui renvoie des mots fixes par piste, `cache_path` dans `tmp_path`) :
  - `test_marker_and_filler_in_result` : Julien dit la phrase de coupe à 20 s et un « euh » à 40 s → un événement `CUT_REQUEST`, un « euh » coupé, timecodes Final décalés par les deux coupes.
  - `test_bleed_word_counted_once` : les mêmes mots du marqueur reviennent sur la piste de Franck, hors de sa parole propre → un seul événement, piste Julien.
  - `test_euh_between_pauses_leaves_one_short_pause` : pause de 0,7 s, « euh » de 0,4 s, pause de 0,7 s, personne d'autre ne parle → la carte des coupes laisse `silence_target_s` (0,4 s) de ces 1,8 s.
  - `test_second_run_reads_the_cache` : le deuxième `analyze` avec un moteur qui lève une exception → même résultat, `transcription.cached_tracks == 2`.
  - `test_mixed_layout_fillers` : un seul fichier voix, un mot qui chevauche un « euh » → ce « euh » signalé `"Other speech at the same time"`, un « euh » isolé coupé.
- [ ] **Étape 2 : tests lents** sur `samples/pedit` (sautés sans les fichiers) : les valeurs attendues du M1 tiennent toujours (3 chevauchements, 1 extrait de film, blancs) et les nombres de marqueurs et de « euh » notés à l'étape 5 sont trouvés ; idem sur un fichier mélangé construit dans `tmp_path` avec ffmpeg (`amix` des deux voix).
- [ ] **Étapes 3 et 4 :** ÉCHEC → mise en œuvre → `uv run pytest` et `uv run pytest -m slow` → SUCCÈS.
- [ ] **Étape 5 : vérification sur l'enregistrement de test, avec Julien** : `uv run pedit run --voice samples/pedit/pedit-full-piste-1-julien.wav --voice samples/pedit/pedit-full-piste-2-franck.wav --film samples/pedit/pedit-full-piste-3-film.wav --out out/pedit --dry-run`, deux fois (la deuxième lit le cache). Noter le temps de transcription. Julien donne les moments des marqueurs et des « euh » qu'il entend ; comparer au `.md`, ajuster les valeurs par défaut qui ratent (invite, `marker_min_score`, `filler_pad_s`, `filler_snap_s`), fixer les nombres dans le test lent et noter les valeurs retenues dans le tableau « Réglages validés » de `CLAUDE.md`.
- [ ] **Étape 6 :** README (deux langues) : le premier passage télécharge le modèle Whisper ; ce que contient désormais le fichier de montage. CHANGELOG (deux langues) : les entrées du M2.
- [ ] **Étape 7 :** commit `feat(pipeline): transcription, markers and hesitations in run --dry-run / transcription, marqueurs et hésitations dans run --dry-run`.
