# M1 : fondations et analyse, plan d'implémentation

*[English version](2026-11-05-m1-foundations-analysis.md)*

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** une CLI `podcleaner run … --dry-run` qui lit les deux pistes voix et la piste film d'un épisode, détecte les blancs, les chevauchements et les extraits de film, et écrit le fichier de montage `.md` avec les timecodes sur l'audio original et sur l'audio final prévu.

**Architecture :** paquet Python `src/podcleaner/`. Les entrées/sorties (ffmpeg, Silero VAD, fichiers) restent en bordure ; toute la détection est faite de fonctions pures sur des listes d'`Interval`, testables sans audio. L'analyse se fait sur une copie mono 16 kHz float32 de chaque piste, décodée par ffmpeg, jamais sur l'audio pleine résolution.

**Tech Stack :** Python 3.11–3.12, uv, Typer, numpy, soundfile, silero-vad (ONNX), ffmpeg/ffprobe (PATH), pytest, Ruff.

**Spec :** [`docs/spec.fr.md`](../../spec.fr.md) · feuille de route : [`2026-11-05-roadmap.fr.md`](2026-11-05-roadmap.fr.md)

## Global Constraints

- Tourne sur macOS et Windows ; chemins via `pathlib`, fichiers texte écrits en `encoding="utf-8"`.
- Aucun compte ni clé d'API requis ; M1 n'appelle aucun service réseau à l'exécution.
- Entrées : WAV uniquement ; toujours 2 pistes voix + 1 piste film.
- Toutes les analyses se font sur l'audio original ; la carte des coupes recale chaque timecode sur le final.
- Blancs : tout silence > 1 s où toutes les pistes se taisent est ramené à environ 0,4 s.
- Chevauchements : timecode seul, aucune modification de volume.
- Un seul fichier `.md` par épisode : partie Timecodes puis partie Rapport.
- `--dry-run` produit le rapport et les timecodes sans écrire d'audio.
- Identifiants du code en anglais ; textes affichés et fichier de montage en français.
- Timecodes au format `HH:MM:SS.mmm`.
- Tests rapides (`pytest -m "not slow"`) sans modèle ni réseau ; les tests qui chargent Silero sont marqués `slow`.
- Chaque tâche se fait sur sa branche et entre dans `main` par pull request ; messages de commit en Conventional Commits, en anglais.
- Documentation en anglais (`nom.md`) et en français (`nom.fr.md`) : toute doc modifiée l'est dans les deux langues.

## Review Focus

1. **Repisse entre micros** : chaque micro capte l'autre voix ; sans filtre, toute parole devient un chevauchement. Une piste ne compte comme active que si son niveau dépasse celui de l'autre voix moins `bleed_margin_db` (10 dB). Test dans la tâche 5.
2. **Rires, respirations, « mmh »** : Silero ne les classe pas toujours comme parole ; ils ne doivent pas être raccourcis comme des blancs. Un blanc exige aussi qu'aucune piste ne dépasse son bruit de fond + 12 dB. Test dans la tâche 7.
3. **Pistes de durées ou fréquences différentes** (enregistrement lancé à des moments différents) : écart de durée > 2 s → erreur claire ; fréquences différentes acceptées. Test dans la tâche 4.
4. **Chemins avec espaces et accents, WAV stéréo / 24 bits / float 32** : doivent se lire sans erreur. Test dans la tâche 4.
5. **ffmpeg absent du PATH** : message en français qui dit quoi installer, code de sortie 2, pas de trace Python. Test dans la tâche 4.

---

## Fichiers

```
pyproject.toml, uv.lock, CLAUDE.md
.gitignore, README.md / README.fr.md   (déjà présents : complétés)
.github/workflows/ci.yml
.claude/hooks/python_checks.py         (modifié : passe par uv run)
src/podcleaner/__init__.py             __version__
src/podcleaner/cli.py                  app Typer : version, run
src/podcleaner/errors.py               PodcleanerError (message utilisateur, code 2)
src/podcleaner/timeline.py             Interval et opérations, format_tc
src/podcleaner/config.py               Settings + chargement TOML
src/podcleaner/audio_io.py             probe, decode_mono_16k, frame_levels
src/podcleaner/episode.py              Episode, load_episode
src/podcleaner/analysis/vad.py         speech_intervals (Silero)
src/podcleaner/analysis/activity.py    own_speech, loud_intervals, noise_floor_db
src/podcleaner/analysis/film.py        film_activity, film_clips
src/podcleaner/detect/silences.py      find_silence_cuts
src/podcleaner/detect/overlaps.py      find_overlap_attempts
src/podcleaner/events.py               EventType, Event (tâche 8)
src/podcleaner/cutmap.py               CutMap
src/podcleaner/report/markdown.py      render_edit_file
src/podcleaner/pipeline.py             analyze, run
tests/…                                un fichier de test par module, tests/data/ pour la parole
```

---

### Task 1 : socle du dépôt et CLI minimale

**Files :**
- Create : `pyproject.toml`, `CLAUDE.md`, `.github/workflows/ci.yml`, `src/podcleaner/__init__.py`, `src/podcleaner/cli.py`, `src/podcleaner/errors.py`, `tests/test_cli.py`
- Modify : `.claude/hooks/python_checks.py`

**Interfaces :**
- Produces : `podcleaner.__version__: str = "0.1.0"` ; `podcleaner.cli.app: typer.Typer` ; `class PodcleanerError(Exception)` dont le message est affiché tel quel par la CLI, qui sort alors avec le code 2.

- [ ] **Step 1 :** installer uv (`brew install uv`), créer une branche `chore/scaffold`, `uv init --package --python 3.12` (le dépôt, `.gitignore`, `LICENSE` et les README existent déjà : ne pas les écraser). `pyproject.toml` : `requires-python = ">=3.11,<3.13"`, script `podcleaner = "podcleaner.cli:app"`, dépendances `typer`, `numpy`, `soundfile`, `silero-vad`, `onnxruntime` ; groupe dev `pytest`, `ruff`. Ruff : `line-length = 100`, règles `E,F,I,UP,B`. pytest : `markers = ["slow: charge un modèle"]`, `addopts = "-m 'not slow'"`.
- [ ] **Step 2 :** vérifier que `.gitignore` couvre `.venv/`, `samples/`, `out/`, `*.wav` sauf `tests/data/*.wav` (déjà le cas).
- [ ] **Step 3 : test qui échoue**

```python
def test_version_command_prints_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

def test_podcleaner_error_exits_2_with_message(monkeypatch):
    # une commande qui lève PodcleanerError("Fichier introuvable : x.wav")
    # → exit_code == 2, le message est dans la sortie, pas de "Traceback"
```

- [ ] **Step 4 :** `uv run pytest` → FAIL (module absent).
- [ ] **Step 5 :** implémenter `cli.py` : commande `version`, et un point d'entrée qui attrape `PodcleanerError`, affiche `Erreur : <message>` sur stderr et sort avec 2.
- [ ] **Step 6 :** `uv run pytest` → PASS.
- [ ] **Step 7 :** hook : si `uv.lock` existe à la racine, lancer `uv run ruff …` et `uv run pytest -q -x -m "not slow"` ; sinon garder le comportement actuel. Vérifier en éditant un fichier `.py` : le hook passe.
- [ ] **Step 8 :** `CLAUDE.md` : reprendre en liste les décisions de la spec (tableau « Décisions », points de vigilance, sorties) + commandes `uv run pytest`, `uv run pytest -m slow`, `uv run ruff check`. CI : matrice `macos-latest`, `windows-latest`, Python 3.11 et 3.12, `astral-sh/setup-uv`, `FedericoCarboni/setup-ffmpeg`, puis `uv run ruff check` et `uv run pytest`.
- [ ] **Step 9 :** commit `chore: project scaffold, minimal CLI, CI`.

---

### Task 2 : intervalles et timecodes

**Files :** Create `src/podcleaner/timeline.py`, `tests/test_timeline.py`

**Interfaces :**
- Produces :
  - `@dataclass(frozen=True, order=True) class Interval: start: float; end: float` (secondes ; `ValueError` si `end < start`) ; propriété `duration`.
  - `merge(intervals: Iterable[Interval], max_gap: float = 0.0) -> list[Interval]` : trie et fusionne ceux séparés de ≤ `max_gap`.
  - `union(*lists: Iterable[Interval]) -> list[Interval]`
  - `intersect(a: list[Interval], b: list[Interval]) -> list[Interval]`
  - `invert(intervals: list[Interval], total: float) -> list[Interval]` : les trous dans `[0, total]`.
  - `format_tc(seconds: float) -> str`

- [ ] **Step 1 : tests qui échouent**

```python
def test_merge_joins_close_intervals():
    assert merge([I(0, 1), I(1.2, 2), I(5, 6)], max_gap=0.3) == [I(0, 2), I(5, 6)]

def test_union_and_intersect():
    assert union([I(0, 2)], [I(1, 3)]) == [I(0, 3)]
    assert intersect([I(0, 2), I(4, 6)], [I(1, 5)]) == [I(1, 2), I(4, 5)]

def test_invert_returns_gaps_within_total():
    assert invert([I(1, 2), I(3, 4)], total=5) == [I(0, 1), I(2, 3), I(4, 5)]
    assert invert([], total=5) == [I(0, 5)]

def test_format_tc():
    assert format_tc(0) == "00:00:00.000"
    assert format_tc(7803.4567) == "02:10:03.457"

def test_interval_rejects_negative_duration():
    with pytest.raises(ValueError): I(2, 1)
```

- [ ] **Step 2 :** lancer → FAIL. **Step 3 :** implémenter. **Step 4 :** lancer → PASS.
- [ ] **Step 5 :** commit `feat(timeline): intervals and timecodes`.

---

### Task 3 : réglages

**Files :** Create `src/podcleaner/config.py`, `tests/test_config.py`

**Interfaces :**
- Produces : `@dataclass(frozen=True) class Settings` avec ces champs et défauts :

| Champ | Défaut | Source |
| --- | --- | --- |
| `silence_min_s` | 1.0 | spec |
| `silence_target_s` | 0.4 | spec |
| `fade_ms` | 30 | choix (utilisé en M3) |
| `vad_threshold` | 0.5 | défaut Silero |
| `vad_min_speech_ms` | 250 | défaut Silero |
| `vad_min_silence_ms` | 100 | défaut Silero |
| `level_hop_s` | 0.01 | choix |
| `bleed_margin_db` | 10.0 | Review Focus 1 |
| `activity_above_floor_db` | 12.0 | Review Focus 2 |
| `film_threshold_dbfs` | -45.0 | choix, à régler sur un épisode |
| `film_merge_gap_s` | 2.0 | choix |
| `film_min_clip_s` | 3.0 | choix |
| `overlap_min_s` | 0.4 | choix |
| `overlap_floor_hold_s` | 1.0 | choix |
| `overlap_merge_gap_s` | 0.3 | choix |
| `max_duration_mismatch_s` | 2.0 | Review Focus 3 |

  `load_settings(path: Path | None) -> Settings` : lit un TOML (`tomllib`), section `[podcleaner]`, ne remplace que les clés présentes.

- [ ] **Step 1 : tests qui échouent** : `test_defaults_match_spec` (`silence_min_s == 1.0`, `silence_target_s == 0.4`) ; `test_toml_overrides_only_given_keys` (fichier avec `silence_target_s = 0.5` → 0.5, reste au défaut) ; `test_unknown_key_raises` → `PodcleanerError` qui cite la clé.
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(config): settings and TOML loading`.

---

### Task 4 : lecture des pistes et épisode

**Files :** Create `src/podcleaner/audio_io.py`, `src/podcleaner/episode.py`, `tests/test_audio_io.py`, `tests/test_episode.py`, `tests/conftest.py`

**Interfaces :**
- Produces :
  - `@dataclass(frozen=True) class AudioInfo: path: Path; duration: float; sample_rate: int; channels: int; codec: str`
  - `probe(path: Path) -> AudioInfo` (ffprobe, sortie JSON)
  - `decode_mono_16k(path: Path) -> np.ndarray` : float32, mono (moyenne des canaux), 16 000 Hz, via `ffmpeg -i … -ac 1 -ar 16000 -f f32le -` lu depuis le pipe.
  - `frame_levels(samples: np.ndarray, sr: int, hop_s: float) -> np.ndarray` : niveau RMS en dBFS par trame de `hop_s`, plancher -120.
  - `require_ffmpeg() -> None` : `PodcleanerError` si `ffmpeg` ou `ffprobe` manque (`shutil.which`).
  - `@dataclass(frozen=True) class Track: label: str; info: AudioInfo`
  - `@dataclass(frozen=True) class Episode: name: str; voice_a: Track; voice_b: Track; film: Track` ; propriété `duration` = la plus courte des trois.
  - `load_episode(voice_a: Path, voice_b: Path, film: Path, name: str, settings: Settings) -> Episode` ; `label` = nom du fichier sans extension.
- Fixture `conftest.py` : `make_wav(path, seconds, sr=48000, channels=1, subtype="PCM_24", signal="silence"|"tone")` avec soundfile.

- [ ] **Step 1 : tests qui échouent**

```python
def test_decode_returns_mono_16k_float32(make_wav, tmp_path):
    p = make_wav(tmp_path / "a.wav", seconds=2, sr=48000, channels=2)
    x = decode_mono_16k(p)
    assert x.dtype == np.float32 and x.ndim == 1 and abs(len(x) - 32000) <= 160

def test_frame_levels_of_full_scale_sine_is_about_minus_3_dbfs(): ...  # ±0.5 dB
def test_frame_levels_of_silence_is_floor(): ...  # == -120

def test_load_episode_accepts_spaces_accents_float32_and_stereo(make_wav, tmp_path):
    d = tmp_path / "Épisode 12 été"
    # voix A PCM_24 mono, voix B FLOAT stéréo, film 44,1 kHz → Episode chargé, labels = noms de fichiers

def test_load_episode_rejects_non_wav(tmp_path): ...       # .mp3 → PodcleanerError "WAV uniquement"
def test_load_episode_rejects_duration_mismatch(): ...     # 10 s vs 13 s → PodcleanerError avec les deux durées
def test_load_episode_missing_file(): ...                  # PodcleanerError qui cite le chemin
def test_require_ffmpeg_missing(monkeypatch): ...          # shutil.which → None ; message contient "ffmpeg" et "installer"
```

- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. Le format est vérifié avec `probe(...).codec` qui commence par `pcm_` (pas sur l'extension seule).
- [ ] **Step 5 :** commit `feat(episode): read WAV tracks and validate the episode`.

---

### Task 5 : détection de parole et activité propre à chaque voix

**Files :** Create `src/podcleaner/analysis/__init__.py`, `analysis/vad.py`, `analysis/activity.py`, `tests/test_activity.py`, `tests/test_vad.py`, `tests/data/speech_*.wav` + `tests/data/ATTRIBUTION.md`

**Interfaces :**
- Consumes : `Interval`, `merge`, `intersect` (tâche 2) ; `Settings` (tâche 3) ; `frame_levels` (tâche 4).
- Produces :
  - `speech_intervals(samples: np.ndarray, settings: Settings) -> list[Interval]` : Silero (`load_silero_vad(onnx=True)` chargé une fois, `get_speech_timestamps(..., sampling_rate=16000, return_seconds=True)`), avec `vad_threshold`, `vad_min_speech_ms`, `vad_min_silence_ms`.
  - `own_speech(vad: list[Interval], levels: np.ndarray, other_levels: np.ndarray, hop_s: float, bleed_margin_db: float) -> list[Interval]` : garde les trames de `vad` où `levels > other_levels - bleed_margin_db`, regroupées en intervalles.
  - `noise_floor_db(levels: np.ndarray) -> float` : 10e centile.
  - `loud_intervals(levels: np.ndarray, hop_s: float, threshold_db: float) -> list[Interval]`

- [ ] **Step 1 : tests rapides qui échouent** (`test_activity.py`, niveaux synthétiques, `hop_s=0.01`)

```python
def test_bleed_is_not_own_speech():
    # A parle seul à -20 dBFS de 0 à 5 s ; B capte la repisse à -38 dBFS ; VAD de B dit "parole" 0–5 s
    assert own_speech(vad_b, lv_b, lv_a, 0.01, 10.0) == []

def test_real_overlap_is_own_speech_on_both():
    # A et B à -20 dBFS de 2 à 3 s → own_speech de B == [I(2, 3)] (± une trame)

def test_noise_floor_and_loud_intervals():
    # bruit à -60 dBFS, un rire à -30 dBFS de 4 à 5,5 s → noise_floor_db ≈ -60,
    # loud_intervals(seuil = plancher + 12) == [I(4, 5.5)]
```

- [ ] **Step 2 : test lent** (`@pytest.mark.slow`) : deux extraits LibriSpeech dev-clean (CC BY 4.0) de ~5 s, 16 kHz mono, concaténés avec 3 s de silence ; `speech_intervals` rend 2 intervalles et aucun ne recouvre le silence central. Attribution dans `tests/data/ATTRIBUTION.md`.
- [ ] **Steps 3–5 :** FAIL → implémenter → `uv run pytest` et `uv run pytest -m slow` → PASS.
- [ ] **Step 6 :** commit `feat(analysis): per-track VAD and bleed filter`.

---

### Task 6 : extraits de film

**Files :** Create `src/podcleaner/analysis/film.py`, `tests/test_film.py`

**Interfaces :**
- Produces :
  - `film_activity(levels: np.ndarray, hop_s: float, threshold_dbfs: float) -> list[Interval]` (brut, sert aux blancs)
  - `film_clips(activity: list[Interval], merge_gap_s: float, min_clip_s: float) -> list[Interval]` (sert aux événements)

- [ ] **Step 1 : tests qui échouent** : `test_clip_with_short_pause_is_one_clip` (actif 10–40 s et 41,5–70 s → `[I(10, 70)]`) ; `test_short_blip_is_ignored` (actif 100–101 s → aucun extrait) ; `test_two_clips_far_apart` (→ deux extraits).
- [ ] **Steps 2–4 :** FAIL → implémenter (`loud_intervals` puis `merge`, puis filtre de durée) → PASS. **Step 5 :** commit `feat(analysis): film clip detection`.

---

### Task 7 : blancs et carte des coupes

**Files :** Create `src/podcleaner/cutmap.py`, `src/podcleaner/detect/__init__.py`, `detect/silences.py`, `tests/test_cutmap.py`, `tests/test_silences.py`

**Interfaces :**
- Consumes : `Interval`, `union`, `invert`.
- Produces :
  - `find_silence_cuts(activities: list[list[Interval]], total: float, settings: Settings) -> list[Interval]` : prend l'union de toutes les activités (voix, sons forts des voix, film), garde les trous > `silence_min_s`, et rend pour chacun la partie à retirer `Interval(gap.start + k, gap.end - k)` avec `k = silence_target_s / 2`. Un trou qui touche 0 ou `total` est traité pareil.
  - `@dataclass(frozen=True) class CutMap: cuts: tuple[Interval, ...]` (triés, disjoints, vérifié à la construction)
    - `to_final(t: float) -> float` : `t` moins la durée coupée avant `t` ; un `t` dans une coupe donne le début de la coupe sur le final.
    - `final_duration(total: float) -> float`
    - `removed() -> float`

- [ ] **Step 1 : tests qui échouent**

```python
def test_long_silence_shortened_to_target():
    cuts = find_silence_cuts([[I(0, 10)], [I(13, 20)]], total=20, settings=S())
    assert cuts == [I(10.2, 12.8)]          # trou de 3 s → 0,4 s gardées

def test_silence_of_exactly_one_second_is_kept():
    assert find_silence_cuts([[I(0, 10), I(11, 20)]], 20, S()) == []

def test_laugh_on_one_track_prevents_cut():
    # voix A : parole 0–10 et 15–20 ; sons forts A (rire) 11–13 → coupes [I(10.2, 10.8), I(13.2, 14.8)]

def test_film_activity_prevents_cut(): ...

def test_cutmap_to_final():
    m = CutMap((I(10, 12), I(20, 25)))
    assert m.to_final(5) == 5 and m.to_final(15) == 13 and m.to_final(30) == 23
    assert m.to_final(11) == 10 and m.final_duration(40) == 33

def test_cutmap_rejects_overlapping_cuts(): ...
```

- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(silences): shorten silences and build the cut map`.

---

### Task 8 : événements et tentatives de prise de parole

**Files :** Create `src/podcleaner/events.py`, `src/podcleaner/detect/overlaps.py`, `tests/test_overlaps.py`

**Interfaces :**
- Consumes : `Interval`, `merge`, `intersect`.
- Produces :
  - `class EventType(StrEnum)` : `CUT_REQUEST = "Coupe demandée"`, `CLIP_TO_ADD = "Extrait à ajouter"`, `FILM_CLIP = "Extrait de film"`, `OVERLAP = "Chevauchement"`, `SUGGESTION = "Suggestion"`. (`CUT_REQUEST`, `CLIP_TO_ADD` et `SUGGESTION` sont remplis en M2 et M5.)
  - `@dataclass(frozen=True) class Event: type: EventType; start: float; end: float; track: str; reason: str; source: Literal["règle", "claude"] = "règle"`
  - `find_overlap_attempts(a: list[Interval], b: list[Interval], label_a: str, label_b: str, settings: Settings) -> list[Event]`.
  Règle, appliquée dans les deux sens : un segment `s` de B est signalé si (1) il commence après le début du segment fusionné de A qui le recouvre, (2) son recouvrement avec A dure ≥ `overlap_min_s`, (3) A, fusionné avec `overlap_merge_gap_s`, couvre encore `[s.end, s.end + overlap_floor_hold_s]`. L'événement porte `track=label_b` et la raison `"<B> tente de parler pendant que <A> parle ; <A> garde la parole"`.

- [ ] **Step 1 : tests qui échouent** : `test_attempt_flagged` (A 0–20, B 5–6 → un événement 5–6, piste B) ; `test_short_backchannel_ignored` (B 5–5,3) ; `test_turn_taking_not_flagged` (A 0–10, B 9,5–20 : A s'arrête) ; `test_symmetric` (A interrompt B → piste A) ; `test_brief_pause_in_a_still_counts_as_holding_floor` (A 0–6 et 6,2–20, B 5–6).
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(overlaps): detect attempts to take the floor`.

---

### Task 9 : fichier de montage

**Files :** Create `src/podcleaner/report/__init__.py`, `report/markdown.py`, `tests/test_markdown.py`

**Interfaces :**
- Consumes : `Event`, `EventType` (tâche 8) ; `Episode` (tâche 4) ; `CutMap` (tâche 7) ; `format_tc` (tâche 2).
- Produces :
  - `@dataclass(frozen=True) class AnalysisResult: episode: Episode; events: list[Event]; silence_cuts: CutMap; dry_run: bool`
  - `render_edit_file(result: AnalysisResult, version: str, generated_on: date) -> str`

Format exact (en-têtes et colonnes) :

```markdown
# <episode.name> : fichier de montage

Généré par podcleaner <version> le <AAAA-MM-JJ> · mode : <dry-run|montage>

## Timecodes

| # | Type | Piste | Original | Final | Durée | Raison |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Extrait de film | <label film> | 00:12:03.120 | 00:11:58.320 | 00:01:22.000 | Activité sur la piste film |

## Rapport

### Pistes

| Piste | Durée | Fréquence | Canaux |

### Blancs

<n> blancs raccourcis, <durée retirée> retirées. Durée finale : <HH:MM:SS.mmm> (originale : <HH:MM:SS.mmm>).

### Avis de Claude

Aucun : traitement sans clé d'API.
```

  Événements triés par `start` ; « Final » = `silence_cuts.to_final(start)` ; aucune ligne de tableau → la ligne `_Aucun événement._` à la place du tableau ; caractères `|` dans une raison échappés en `\|`.

- [ ] **Step 1 : tests qui échouent** : `test_render_matches_expected_snippet` (épisode factice, un extrait de film et un chevauchement, une coupe de blanc avant les deux → colonnes Original et Final attendues, ordre chronologique) ; `test_empty_events_line` ; `test_pipe_in_reason_is_escaped` ; `test_report_counts_silences`.
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(report): Markdown edit file`.

---

### Task 10 : chaîne d'analyse et commande `run --dry-run`

**Files :** Create `src/podcleaner/pipeline.py`, `tests/test_pipeline.py` ; Modify `src/podcleaner/cli.py`, `README.md`, `README.fr.md`

**Interfaces :**
- Consumes : tout ce qui précède.
- Produces :
  - `analyze(episode: Episode, settings: Settings, *, decode=decode_mono_16k, vad=speech_intervals) -> AnalysisResult` (les deux fonctions sont injectables pour les tests). Ordre : décoder les 3 pistes → niveaux → VAD des deux voix → `own_speech` croisé → `loud_intervals` par voix (plancher + `activity_above_floor_db`) → `film_activity` / `film_clips` → `find_silence_cuts` sur `[own_a, own_b, loud_a, loud_b, film_activity]` → `find_overlap_attempts` → événements `FILM_CLIP` (raison `"Activité sur la piste film"`) + `OVERLAP`.
  - `run(...) -> Path` : écrit `<out>/<name>.montage.md` et rend son chemin.
  - CLI : `podcleaner run --voice-a PATH --voice-b PATH --film PATH --out DIR [--name TEXTE] [--config FICHIER] [--dry-run]`. `--name` vaut par défaut le nom du dossier `--out`. Sans `--dry-run`, M1 sort avec `PodcleanerError("Le montage audio arrive dans une prochaine version ; relancez avec --dry-run.")`. Affiche une ligne par étape (`Décodage…`, `Détection de parole…`, …) et le chemin du fichier écrit.

- [ ] **Step 1 : tests qui échouent** : `test_analyze_with_fake_vad` (WAV synthétiques via `make_wav` : tonalité sur le film 30–60 s, VAD factice qui rend des intervalles fixes → un `FILM_CLIP` 30–60 s, les coupes de blanc attendues) ; `test_cli_dry_run_writes_md` (CliRunner, `vad` factice par monkeypatch → fichier `.md` présent, aucun `.wav` écrit dans `--out`) ; `test_cli_without_dry_run_exits_2`.
- [ ] **Step 2 : test lent** : épisode de 20 s construit avec `tests/data/speech_*.wav` sur les deux voix et une tonalité sur le film → la commande réussit et le `.md` contient `Extrait de film`.
- [ ] **Steps 3–5 :** FAIL → implémenter → `uv run pytest` puis `uv run pytest -m slow` → PASS.
- [ ] **Step 6 :** `README.md` et `README.fr.md` : installation (uv, ffmpeg sur macOS via Homebrew, sur Windows via winget), exemple de commande `--dry-run`.
- [ ] **Step 7 : vérification sur un vrai épisode** (manuelle, avec Julien) : lancer sur un épisode brut de `samples/`, noter le temps de calcul et relire le `.md` : extraits de film bien placés, chevauchements plausibles, nombre de blancs cohérent. Ajuster les défauts de `Settings` qui tombent à côté, et noter les valeurs retenues dans `CLAUDE.md`.
- [ ] **Step 8 :** commit `feat(cli): end-to-end run --dry-run command`.
