# M1 : fondations et analyse, plan d'implémentation

**Français** · [English](2026-11-05-m1-foundations-analysis.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** une CLI `pedit run … --dry-run` qui lit un épisode (deux pistes voix, ou une piste stéréo avec les deux voix, plus la piste film), détecte les blancs, les chevauchements et les extraits de film, et écrit le fichier de montage `.md` avec les timecodes sur l'audio original et sur l'audio final prévu ; plus l'assistant `pedit init` et la bannière en pixel art.

**Architecture :** paquet Python `src/podcleaner_editor/`. Les entrées/sorties (ffmpeg, Silero VAD, fichiers, console) restent en bordure ; toute la détection est faite de fonctions pures sur des listes d'`Interval`, testables sans audio. L'analyse se fait sur une copie mono 16 kHz float32 de chaque piste, décodée par ffmpeg, jamais sur l'audio pleine résolution. L'allure de la CLI (bannière, assistant, fichier de configuration) suit podcleaner-clips (`~/dev/podcleaner-clips`, modules `banner.py`, `wizard.py`, `config.py`, `claude.py`), adaptée plutôt qu'importée.

**Tech Stack :** Python 3.11–3.12, uv, Typer, Rich, platformdirs, numpy, soundfile, silero-vad (ONNX), ffmpeg/ffprobe (PATH), pytest, Ruff.

**Spec :** [`docs/spec.fr.md`](../../spec.fr.md) (fait foi) · feuille de route : [`2026-11-05-roadmap.fr.md`](2026-11-05-roadmap.fr.md)

## Global Constraints

- Tourne sur macOS et Windows ; chemins via `pathlib`, jamais en dur ; fichiers texte écrits en `encoding="utf-8"`.
- Claude n'est pas nécessaire ; M1 n'appelle aucun service réseau à l'exécution. Claude ne passe jamais que par la CLI Claude Code connectée, jamais par une clé d'API ni le SDK `anthropic`.
- Entrées : WAV uniquement. Forme `separate` = 2 WAV voix + 1 WAV film ; forme `mixed` = 1 WAV avec les deux voix + 1 WAV film.
- Forme `mixed` : pas de détection des chevauchements ; tout le reste tourne.
- Toutes les analyses se font sur l'audio original ; la carte des coupes recale chaque timecode sur le final.
- Blancs : tout silence > 1 s où toutes les pistes se taisent est ramené à environ 0,4 s.
- Chevauchements : timecode seul, aucune modification de volume.
- Un seul fichier `.md` par épisode : partie Timecodes puis partie Report.
- `--dry-run` produit le rapport et les timecodes sans écrire d'audio.
- Tout en anglais : identifiants, commentaires, docstrings, messages, erreurs, aide de la CLI, fichier de montage, clés de configuration.
- Timecodes au format `HH:MM:SS.mmm`.
- Tests rapides (`pytest -m "not slow"`) sans modèle ni réseau ; les tests qui chargent Silero sont marqués `slow`.
- Chaque tâche se fait sur sa branche et entre dans `main` par pull request ; titres de commit et de PR `type(portée): English / français`, description de PR en anglais puis en français, chacune avec son `## TL;DR` (`.github/pull_request_template.md`).
- Documentation en anglais (`nom.md`) et en français (`nom.fr.md`) : toute doc modifiée l'est dans les deux langues.

## Review Focus

1. **Repisse entre micros** : chaque micro capte l'autre voix ; sans filtre, toute parole devient un chevauchement. Une piste ne compte comme active que si son niveau dépasse celui de l'autre voix moins `bleed_margin_db` (10 dB). Test dans la tâche 5.
2. **Rires, respirations, « mmh »** : Silero ne les classe pas toujours comme parole ; ils ne doivent pas être raccourcis comme des blancs. Un blanc exige aussi qu'aucune piste ne dépasse son bruit de fond + 12 dB. Test dans la tâche 7.
3. **Forme `mixed`** : un seul fichier de voix doit faire tourner toute l'analyse sans chevauchements et le dire dans le rapport, sans jamais comparer la piste à elle-même. Tests dans les tâches 4, 9 et 10.
4. **Pistes de durées ou fréquences différentes** (enregistrement lancé à des moments différents) : écart de durée > 2 s → erreur claire ; fréquences différentes acceptées. Test dans la tâche 4.
5. **Chemins avec espaces et accents, WAV stéréo / 24 bits / float 32, ffmpeg absent** : lecture sans erreur ; un ffmpeg absent donne un message qui dit quoi installer, code de sortie 2, pas de trace Python. Test dans la tâche 4.

---

## Fichiers

```
pyproject.toml, uv.lock, .python-version
.github/workflows/ci.yml               (copié de podcleaner-clips)
.claude/settings.json, .claude/skills/graphify/, .gitignore   (installation graphify de podcleaner-clips)
src/podcleaner_editor/__init__.py      __version__, prog_name
src/podcleaner_editor/cli.py           app Typer : init, run, config, version ; main()
src/podcleaner_editor/errors.py        EditorError (message utilisateur, code 2)
src/podcleaner_editor/banner.py        titre en pixel art
src/podcleaner_editor/wizard.py        questions de init
src/podcleaner_editor/claude_cli.py    find_cli, cli_logged_in (complété en M5)
src/podcleaner_editor/timeline.py      Interval et opérations, format_tc
src/podcleaner_editor/config.py        Settings, lecture TOML, chemin de la config, modèle commenté
src/podcleaner_editor/audio_io.py      probe, decode_mono_16k, frame_levels
src/podcleaner_editor/episode.py       Track, Episode, load_episode
src/podcleaner_editor/analysis/vad.py       speech_intervals (Silero)
src/podcleaner_editor/analysis/activity.py  own_speech, loud_intervals, noise_floor_db
src/podcleaner_editor/analysis/film.py      film_activity, film_clips
src/podcleaner_editor/detect/silences.py    find_silence_cuts
src/podcleaner_editor/detect/overlaps.py    find_overlap_attempts
src/podcleaner_editor/events.py        EventType, Event
src/podcleaner_editor/cutmap.py        CutMap
src/podcleaner_editor/report/markdown.py    AnalysisResult, render_edit_file
src/podcleaner_editor/pipeline.py      analyze, run
tests/…                                un fichier de test par module, tests/data/ pour la parole
```

---

### Task 1 : socle du dépôt et CLI minimale

**Files :**
- Create : `pyproject.toml`, `.python-version` (`3.12`), `.github/workflows/ci.yml`, `src/podcleaner_editor/__init__.py`, `src/podcleaner_editor/cli.py`, `src/podcleaner_editor/errors.py`, `tests/test_cli.py`
- Modify : `.claude/settings.json`, `.gitignore`, `CONTRIBUTING.md` / `CONTRIBUTING.fr.md` (graphify)

**Interfaces :**
- Produces : `podcleaner_editor.__version__: str = "0.1.0"` ; `podcleaner_editor.cli.app: typer.Typer` ; `podcleaner_editor.cli.main() -> None` ; `class EditorError(Exception)` dont `main()` affiche le message sous la forme `Error: <message>` sur stderr, puis sort avec le code 2.

- [ ] **Step 1 :** installer uv (`brew install uv`), `uv init --package --python 3.12` sans écraser les fichiers existants. `pyproject.toml` sur le modèle de podcleaner-clips : `name = "podcleaner-editor"`, `license = "MIT"`, `authors = [{ name = "Julien Gaudet" }]`, `requires-python = ">=3.11,<3.13"`, scripts `podcleaner-editor = "podcleaner_editor.cli:main"` et `pedit = "podcleaner_editor.cli:main"`, dépendances `typer`, `rich`, `platformdirs`, `numpy`, `soundfile`, `silero-vad`, `onnxruntime` ; groupe dev `pytest`, `ruff` ; backend de build `uv_build`. Ruff : `line-length = 100`, `target-version = "py311"`, `extend-exclude = ["docs"]`, règles `E,F,I,UP,B`, isort `known-first-party = ["podcleaner_editor"]`. pytest : `testpaths = ["tests"]`, `markers = ["slow: loads a model"]`, `addopts = "-m 'not slow'"`.
- [ ] **Step 2 : tests qui échouent**

```python
def test_version_command_prints_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0 and "0.1.0" in result.output

def test_version_option():
    assert "0.1.0" in CliRunner().invoke(app, ["--version"]).output

def test_command_alone_prints_help():
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0 and "run" in result.output

def test_editor_error_exits_2_with_message(monkeypatch, capsys):
    # main() sur une commande qui lève EditorError("File not found: x.wav")
    # → SystemExit(2), "Error: File not found: x.wav" sur stderr, pas de "Traceback"
```

- [ ] **Step 3 :** `uv run pytest` → FAIL (module absent).
- [ ] **Step 4 :** implémenter `cli.py` : la commande `version` et l'option `--version`, l'aide quand la commande est lancée seule (`invoke_without_command=True`), et `main()` qui attrape `EditorError`.
- [ ] **Step 5 :** `uv run pytest` → PASS. Modifier un fichier `.py` et vérifier que le hook (`.claude/hooks/python_checks.py`, déjà la version de podcleaner-clips) lance Ruff et pytest via `uv run`.
- [ ] **Step 6 :** CI : copier `ci.yml` de podcleaner-clips (macOS + Windows, Python 3.11 et 3.12, ffmpeg par brew/choco, `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest`). graphify : copier de podcleaner-clips les hooks `PreToolUse` / `SessionStart` de `.claude/settings.json`, `.claude/skills/graphify/`, les entrées `graphify-out/` du `.gitignore` et la section « Working with Claude Code (graphify) » des deux CONTRIBUTING ; lancer `graphify update .`.
- [ ] **Step 7 :** commit `chore: project scaffold, minimal CLI, CI / socle du projet, CLI minimale, CI`.

---

### Task 2 : intervalles et timecodes

**Files :** Create `src/podcleaner_editor/timeline.py`, `tests/test_timeline.py`

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
- [ ] **Step 5 :** commit `feat(timeline): intervals and timecodes / intervalles et timecodes`.

---

### Task 3 : réglages et fichier de configuration

**Files :** Create `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces :**
- Produces :
  - `Layout = Literal["separate", "mixed"]`
  - `@dataclass(frozen=True) class Settings`, champs et défauts, regroupés par la section TOML d'où ils sont lus :

| Clé TOML | Champ | Défaut | Source |
| --- | --- | --- | --- |
| `[paths] output_dir` | `output_dir: Path \| None` | `None` | spec (fichier par personne) |
| `[recording] layout` | `layout: Layout` | `"separate"` | spec |
| `[recording] speakers` | `speakers: tuple[str, str]` | `("Voice A", "Voice B")` | choix |
| `[silences] min_s` | `silence_min_s` | 1.0 | spec |
| `[silences] target_s` | `silence_target_s` | 0.4 | spec |
| `[silences] fade_ms` | `fade_ms` | 30 | choix (utilisé en M3) |
| `[vad] threshold` | `vad_threshold` | 0.5 | défaut Silero |
| `[vad] min_speech_ms` | `vad_min_speech_ms` | 250 | défaut Silero |
| `[vad] min_silence_ms` | `vad_min_silence_ms` | 100 | défaut Silero |
| `[levels] hop_s` | `level_hop_s` | 0.01 | choix |
| `[levels] bleed_margin_db` | `bleed_margin_db` | 10.0 | Review Focus 1 |
| `[levels] above_floor_db` | `activity_above_floor_db` | 12.0 | Review Focus 2 |
| `[film] threshold_dbfs` | `film_threshold_dbfs` | -45.0 | choix, à régler sur un épisode |
| `[film] merge_gap_s` | `film_merge_gap_s` | 2.0 | choix |
| `[film] min_clip_s` | `film_min_clip_s` | 3.0 | choix |
| `[overlaps] min_s` | `overlap_min_s` | 0.4 | choix |
| `[overlaps] floor_hold_s` | `overlap_floor_hold_s` | 1.0 | choix |
| `[overlaps] merge_gap_s` | `overlap_merge_gap_s` | 0.3 | choix |
| `[episode] max_duration_mismatch_s` | `max_duration_mismatch_s` | 2.0 | Review Focus 4 |
| `[claude] enabled` | `claude_enabled` | `True` | spec (utilisé en M5) |
| `[claude] model` | `claude_model` | `"claude-sonnet-5-5"` | comme podcleaner-clips |

  - `CONFIG_ENV_VAR = "PODCLEANER_EDITOR_CONFIG"`
  - `resolve_config_path(cli_path: Path | None) -> Path` : `--config`, sinon la variable d'environnement, sinon `platformdirs.user_config_dir("podcleaner-editor") / "config.toml"`.
  - `load_settings(path: Path) -> Settings` : fichier absent → défauts ; ne remplace que les clés présentes.
  - `settings_values(s: Settings) -> dict[str, Any]` et `render_template(values: dict[str, Any]) -> str` : le fichier TOML commenté (une ligne de commentaire en anglais au-dessus de chaque clé), écrit par `init`.

- [ ] **Step 1 : tests qui échouent** : `test_defaults_match_spec` (`silence_min_s == 1.0`, `silence_target_s == 0.4`, `layout == "separate"`) ; `test_toml_overrides_only_given_keys` (`[silences] target_s = 0.5` → 0.5, le reste au défaut) ; `test_unknown_key_raises` → `EditorError` qui cite `[section] clé` ; `test_bad_layout_raises` (`layout = "stereo"` → `EditorError` qui liste `separate`, `mixed`) ; `test_config_path_precedence` (option > variable d'environnement > dossier utilisateur) ; `test_template_round_trips` (`load_settings` de `render_template(settings_values(s))` redonne `s`).
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(config): settings and configuration file / réglages et fichier de configuration`.

---

### Task 4 : lecture des pistes et épisode

**Files :** Create `src/podcleaner_editor/audio_io.py`, `src/podcleaner_editor/episode.py`, `tests/test_audio_io.py`, `tests/test_episode.py`, `tests/conftest.py`

**Interfaces :**
- Produces :
  - `@dataclass(frozen=True) class AudioInfo: path: Path; duration: float; sample_rate: int; channels: int; codec: str`
  - `probe(path: Path) -> AudioInfo` (ffprobe, sortie JSON)
  - `decode_mono_16k(path: Path) -> np.ndarray` : float32, mono (moyenne des canaux), 16 000 Hz, via `ffmpeg -i … -ac 1 -ar 16000 -f f32le -` lu depuis le pipe.
  - `frame_levels(samples: np.ndarray, sr: int, hop_s: float) -> np.ndarray` : niveau RMS en dBFS par trame de `hop_s`, plancher -120.
  - `require_ffmpeg() -> None` : `EditorError` si `ffmpeg` ou `ffprobe` manque (`shutil.which`).
  - `@dataclass(frozen=True) class Track: label: str; info: AudioInfo`
  - `@dataclass(frozen=True) class Episode: name: str; voices: tuple[Track, ...]; film: Track` ; propriété `layout` (`"separate"` avec 2 voix, `"mixed"` avec 1) ; propriété `duration` = la piste la plus courte.
  - `load_episode(voices: Sequence[Path], film: Path, name: str, settings: Settings) -> Episode`. Étiquettes : `settings.speakers[i]` pour 2 voix, `" + ".join(settings.speakers)` pour une piste mélangée, `"Film"` pour le film.
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
    # voix A PCM_24 mono, voix B FLOAT stéréo, film 44,1 kHz → forme "separate", étiquettes tirées de speakers

def test_one_voice_file_is_mixed_layout(make_wav, tmp_path): ...   # voix stéréo + film → forme "mixed", 1 voix
def test_zero_or_three_voices_rejected(): ...              # EditorError "1 or 2 voice files"
def test_load_episode_rejects_non_wav(tmp_path): ...       # .mp3 → EditorError "WAV only"
def test_load_episode_rejects_duration_mismatch(): ...     # 10 s vs 13 s → EditorError avec les deux durées
def test_load_episode_missing_file(): ...                  # EditorError qui cite le chemin
def test_require_ffmpeg_missing(monkeypatch): ...          # shutil.which → None ; message contient "ffmpeg" et "install"
```

- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. Le format est vérifié avec `probe(...).codec` qui commence par `pcm_` (pas sur l'extension seule).
- [ ] **Step 5 :** commit `feat(episode): read WAV tracks in both layouts / lire les pistes WAV dans les deux formes`.

---

### Task 5 : détection de parole et activité propre à chaque voix

**Files :** Create `src/podcleaner_editor/analysis/__init__.py`, `analysis/vad.py`, `analysis/activity.py`, `tests/test_activity.py`, `tests/test_vad.py`, `tests/data/speech_*.wav` + `tests/data/ATTRIBUTION.md`

**Interfaces :**
- Consumes : `Interval`, `merge`, `intersect` (tâche 2) ; `Settings` (tâche 3) ; `frame_levels` (tâche 4).
- Produces :
  - `speech_intervals(samples: np.ndarray, settings: Settings) -> list[Interval]` : Silero (`load_silero_vad(onnx=True)` chargé une fois, `get_speech_timestamps(..., sampling_rate=16000, return_seconds=True)`), avec `vad_threshold`, `vad_min_speech_ms`, `vad_min_silence_ms`.
  - `own_speech(vad: list[Interval], levels: np.ndarray, other_levels: np.ndarray, hop_s: float, bleed_margin_db: float) -> list[Interval]` : garde les trames de `vad` où `levels > other_levels - bleed_margin_db`, regroupées en intervalles. Pas utilisé dans la forme `mixed`.
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
- [ ] **Step 6 :** commit `feat(analysis): per-track VAD and bleed filter / VAD par piste et filtre de repisse`.

---

### Task 6 : extraits de film

**Files :** Create `src/podcleaner_editor/analysis/film.py`, `tests/test_film.py`

**Interfaces :**
- Produces :
  - `film_activity(levels: np.ndarray, hop_s: float, threshold_dbfs: float) -> list[Interval]` (brut, sert aux blancs)
  - `film_clips(activity: list[Interval], merge_gap_s: float, min_clip_s: float) -> list[Interval]` (sert aux événements)

- [ ] **Step 1 : tests qui échouent** : `test_clip_with_short_pause_is_one_clip` (actif 10–40 s et 41,5–70 s → `[I(10, 70)]`) ; `test_short_blip_is_ignored` (actif 100–101 s → aucun extrait) ; `test_two_clips_far_apart` (→ deux extraits).
- [ ] **Steps 2–4 :** FAIL → implémenter (`loud_intervals` puis `merge`, puis filtre de durée) → PASS. **Step 5 :** commit `feat(analysis): film clip detection / repérage des extraits de film`.

---

### Task 7 : blancs et carte des coupes

**Files :** Create `src/podcleaner_editor/cutmap.py`, `src/podcleaner_editor/detect/__init__.py`, `detect/silences.py`, `tests/test_cutmap.py`, `tests/test_silences.py`

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

- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(silences): shorten silences and build the cut map / raccourcir les blancs et construire la carte des coupes`.

---

### Task 8 : événements et tentatives de prise de parole

**Files :** Create `src/podcleaner_editor/events.py`, `src/podcleaner_editor/detect/overlaps.py`, `tests/test_overlaps.py`

**Interfaces :**
- Consumes : `Interval`, `merge`, `intersect`.
- Produces :
  - `class EventType(StrEnum)` : `CUT_REQUEST = "Requested cut"`, `CLIP_TO_ADD = "Clip to add"`, `FILM_CLIP = "Film clip"`, `OVERLAP = "Overlap"`, `SUGGESTION = "Suggestion"`. (`CUT_REQUEST`, `CLIP_TO_ADD` et `SUGGESTION` sont remplis en M2 et M5.)
  - `@dataclass(frozen=True) class Event: type: EventType; start: float; end: float; track: str; reason: str; source: Literal["rule", "claude"] = "rule"`
  - `find_overlap_attempts(a: list[Interval], b: list[Interval], label_a: str, label_b: str, settings: Settings) -> list[Event]`.
  Règle, appliquée dans les deux sens : un segment `s` de B est signalé si (1) il commence après le début du segment fusionné de A qui le recouvre, (2) son recouvrement avec A dure ≥ `overlap_min_s`, (3) A, fusionné avec `overlap_merge_gap_s`, couvre encore `[s.end, s.end + overlap_floor_hold_s]`. L'événement porte `track=label_b` et la raison `"<B> tries to speak while <A> is speaking; <A> keeps the floor"`.

- [ ] **Step 1 : tests qui échouent** : `test_attempt_flagged` (A 0–20, B 5–6 → un événement 5–6, piste B) ; `test_short_backchannel_ignored` (B 5–5,3) ; `test_turn_taking_not_flagged` (A 0–10, B 9,5–20 : A s'arrête) ; `test_symmetric` (A interrompt B → piste A) ; `test_brief_pause_in_a_still_counts_as_holding_floor` (A 0–6 et 6,2–20, B 5–6).
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(overlaps): detect attempts to take the floor / repérer les tentatives de prise de parole`.

---

### Task 9 : fichier de montage

**Files :** Create `src/podcleaner_editor/report/__init__.py`, `report/markdown.py`, `tests/test_markdown.py`

**Interfaces :**
- Consumes : `Event`, `EventType` (tâche 8) ; `Episode` (tâche 4) ; `CutMap` (tâche 7) ; `format_tc` (tâche 2).
- Produces :
  - `@dataclass(frozen=True) class AnalysisResult: episode: Episode; events: list[Event]; silence_cuts: CutMap; dry_run: bool`
  - `render_edit_file(result: AnalysisResult, version: str, generated_on: date) -> str`

Format exact (en-têtes et colonnes ; le fichier est en anglais) :

```markdown
# <episode.name>: edit file

Generated by podcleaner-editor <version> on <YYYY-MM-DD> · mode: <dry run|edit> · layout: <separate tracks|mixed voices>

## Timecodes

| # | Type | Track | Original | Final | Duration | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Film clip | Film | 00:12:03.120 | 00:11:58.320 | 00:01:22.000 | Activity on the film track |

## Report

### Tracks

| Track | File | Duration | Sample rate | Channels |

### Silences

<n> silences shortened, <removed duration> removed. Final duration: <HH:MM:SS.mmm> (original: <HH:MM:SS.mmm>).

### Overlaps

<n> attempts to take the floor flagged.        ← forme separate
Not available: both voices are on one track.   ← forme mixed

### Claude's opinions

None: processed without Claude.
```

  Événements triés par `start` ; « Final » = `silence_cuts.to_final(start)` ; aucune ligne de tableau → la ligne `_No events._` à la place du tableau ; caractères `|` dans une raison échappés en `\|`.

- [ ] **Step 1 : tests qui échouent** : `test_render_matches_expected_snippet` (épisode factice, un extrait de film et un chevauchement, une coupe de blanc avant les deux → colonnes Original et Final attendues, ordre chronologique) ; `test_empty_events_line` ; `test_pipe_in_reason_is_escaped` ; `test_report_counts_silences` ; `test_mixed_layout_says_overlaps_not_available`.
- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. **Step 5 :** commit `feat(report): Markdown edit file / fichier de montage Markdown`.

---

### Task 10 : chaîne d'analyse et commande `run --dry-run`

**Files :** Create `src/podcleaner_editor/pipeline.py`, `tests/test_pipeline.py` ; Modify `src/podcleaner_editor/cli.py`, `README.md`, `README.fr.md`

**Interfaces :**
- Consumes : tout ce qui précède.
- Produces :
  - `analyze(episode: Episode, settings: Settings, *, decode=decode_mono_16k, vad=speech_intervals, progress: Callable[[str], None] = lambda _: None) -> AnalysisResult` (`decode` et `vad` injectables pour les tests).
    - Forme `separate` : décoder les 3 pistes → niveaux → VAD des deux voix → `own_speech` croisé → `loud_intervals` par voix (plancher + `activity_above_floor_db`) → `film_activity` / `film_clips` → `find_silence_cuts` sur `[own_a, own_b, loud_a, loud_b, film_activity]` → `find_overlap_attempts` → événements `FILM_CLIP` (raison `"Activity on the film track"`) + `OVERLAP`.
    - Forme `mixed` : VAD brute et `loud_intervals` de la piste des voix (pas d'`own_speech`), blancs sur `[vad, loud, film_activity]`, pas de détection des chevauchements, événements `FILM_CLIP`.
  - `run(...) -> Path` : écrit `<out>/<name>.edit.md` et rend son chemin.
  - CLI : `pedit run --voice PATH [--voice PATH] --film PATH [--out DIR] [--name TEXT] [--config FILE] [--dry-run]`. Un `--voice` = forme `mixed`, deux = `separate` ; si cela contredit `[recording] layout`, les fichiers l'emportent et un avis `⚠` le dit. `--name` vaut par défaut le nom du dossier `--out` ; sans `--out`, `--name` est obligatoire et la sortie va dans `<output_dir>/<name>` (`EditorError` si `output_dir` n'est pas réglé non plus : « run `pedit init` or pass --out »). Sans `--dry-run`, M1 sort avec `EditorError("Writing the edited audio comes in a later version; run again with --dry-run.")`. Affiche une ligne par étape (`Decoding…`, `Detecting speech…`, …) et le chemin du fichier écrit.

- [ ] **Step 1 : tests qui échouent** : `test_analyze_with_fake_vad` (WAV synthétiques via `make_wav` : tonalité sur le film 30–60 s, VAD factice qui rend des intervalles fixes → un `FILM_CLIP` 30–60 s, les coupes de blanc attendues) ; `test_analyze_mixed_layout` (un seul fichier de voix → aucun événement `OVERLAP`, les coupes de blanc attendues pour la VAD factice) ; `test_cli_dry_run_writes_md` (CliRunner, `vad` factice par monkeypatch → fichier `.md` présent, aucun `.wav` écrit dans `--out`) ; `test_cli_without_dry_run_exits_2` ; `test_cli_needs_out_or_output_dir`.
- [ ] **Step 2 : test lent** : épisode de 20 s construit avec `tests/data/speech_*.wav` sur les deux voix et une tonalité sur le film → la commande réussit et le `.md` contient `Film clip` ; pareil avec un seul fichier de voix mélangées.
- [ ] **Steps 3–5 :** FAIL → implémenter → `uv run pytest` puis `uv run pytest -m slow` → PASS.
- [ ] **Step 6 :** `README.md` et `README.fr.md` : installation (`uv tool install …`, ffmpeg sur macOS via Homebrew, sur Windows via winget), exemples de commande `--dry-run` dans les deux formes.
- [ ] **Step 7 : vérification sur un vrai épisode** (manuelle, avec Julien) : lancer sur un épisode brut de `samples/`, noter le temps de calcul et relire le `.md` : extraits de film bien placés, chevauchements plausibles, nombre de blancs cohérent. Ajuster les défauts de `Settings` qui tombent à côté, et noter les valeurs retenues dans `CLAUDE.md`.
- [ ] **Step 8 :** commit `feat(cli): end-to-end run --dry-run command / commande run --dry-run de bout en bout`.

---

### Task 11 : bannière, assistant `init` et commande `config`

**Files :** Create `src/podcleaner_editor/banner.py`, `src/podcleaner_editor/wizard.py`, `src/podcleaner_editor/claude_cli.py`, `tests/test_banner.py`, `tests/test_wizard.py`, `tests/test_claude_cli.py` ; Modify `src/podcleaner_editor/cli.py`, `README.md`, `README.fr.md`

**Interfaces :**
- Consumes : `Settings`, `resolve_config_path`, `load_settings`, `settings_values`, `render_template` (tâche 3).
- Produces :
  - `banner.py`, adapté de podcleaner-clips : `NAME = "podcleaner-editor"`, `TAGLINE = "edit the episode, keep the timecodes"`, `NO_BANNER_ENV_VAR = "PODCLEANER_EDITOR_NO_BANNER"`, `RUST = "#94380c"`, `CREAM = "#fbf2f1"` ; `pixel_lines(text: str = NAME) -> list[str]` (même police 3×5, plus `"t": ("###", ".#.", ".#.", ".#.", ".#.")`) ; `wanted(ctx) -> bool` ; `show(ctx) -> None`. Affichée au début de `init`, de `run` et de la commande seule ; option racine `--no-banner`.
  - `claude_cli.py`, adapté du `claude.py` de podcleaner-clips : `find_cli() -> str | None` (PATH, puis `~/.local/bin`, `~/.claude/local`) et `cli_logged_in(cli: str, runner=...) -> bool | None` (`claude auth status --json`, clé `loggedIn`). Aucun import d'`anthropic`.
  - `wizard.py` : `run_wizard(path: Path, *, ask: bool) -> Path`. Questions, dans cet ordre, valeurs actuelles par défaut :
    1. Dossier de sortie (un sous-dossier par épisode) ; créé après confirmation s'il manque. Les chemins collés ou glissés sont nettoyés (guillemets, échappements `\ ` de macOS), comme `clean_path` dans podcleaner-clips.
    2. Forme d'enregistrement : `separate` (un fichier par voix) ou `mixed` (un fichier stéréo avec les deux voix).
    3. Prénoms des deux voix.
    4. Utiliser Claude quand il est disponible ? Si `find_cli()` ne trouve rien ou si `cli_logged_in` vaut `False`, le dire d'abord (« Claude Code is not installed / not logged in (run: claude auth login) ») ; la réponse est enregistrée dans tous les cas.
    Ensuite : confirmation avant de remplacer un fichier existant, écriture atomique (fichier temporaire puis `os.replace`), et le chemin affiché. `ask=False` (hors terminal ou `--no-input`) écrit le modèle commenté avec les défauts.
  - CLI : `pedit init [--no-input] [--config FILE]` ; `pedit config [--path] [--config FILE]` affiche le chemin du fichier et chaque `clé = valeur`.

- [ ] **Step 1 : tests qui échouent**

```python
def test_pixel_lines_have_the_same_width():
    lines = pixel_lines()
    assert len(lines) == 4 and len({len(l) for l in lines}) == 1

def test_banner_hidden_outside_a_terminal(capsys): ...        # stdout pas un terminal → rien d'affiché
def test_banner_hidden_by_env_var(monkeypatch): ...           # PODCLEANER_EDITOR_NO_BANNER=1
def test_banner_falls_back_to_one_line_when_narrow(): ...     # 40 colonnes → "podcleaner-editor 0.1.0 - …"

def test_wizard_writes_answers(tmp_path):
    # entrée CliRunner : "<dossier>\nmixed\nJulien\nMarc\ny\n" → load_settings(fichier).layout == "mixed",
    # speakers == ("Julien", "Marc"), output_dir == le dossier
def test_wizard_offers_current_values(tmp_path): ...          # fichier existant + réponses vides → mêmes valeurs
def test_wizard_keeps_file_when_replace_refused(tmp_path): ...
def test_init_no_input_writes_template(tmp_path): ...         # aucune question, fichier == render_template(défauts)
def test_wizard_warns_when_claude_code_is_missing(monkeypatch): ...  # find_cli → None → message affiché
def test_clean_path_strips_quotes_and_escapes(): ...
def test_cli_logged_in_reads_json(): ...                      # runner factice → True / False / None si JSON invalide
def test_config_path_option(tmp_path): ...                    # `pedit config --path` n'affiche que le chemin
```

- [ ] **Steps 2–4 :** FAIL → implémenter → PASS. Vérifier à la main dans un vrai terminal : `uv run pedit`, `uv run pedit init`, et rétrécir la fenêtre pour voir le titre sur une ligne.
- [ ] **Step 5 :** README : une section « Configure » / « Configurer » (`pedit init`, `pedit config`) dans les deux langues.
- [ ] **Step 6 :** commit `feat(cli): pixel-art banner, init wizard and config command / bannière pixel art, assistant init et commande config`.
