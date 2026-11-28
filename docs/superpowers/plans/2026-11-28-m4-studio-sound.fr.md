# M4 : son studio, plan de mise en œuvre

**Français** · [English](2026-11-28-m4-studio-sound.md)

> **Pour les agents :** SOUS-SKILL REQUIS : utiliser superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans pour mettre en œuvre ce plan tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`) pour le suivi.

**Objectif :** `pedit run` sans `--dry-run` traite le son de chaque voix comme Auphonic : DeepFilterNet 3, puis filtres ffmpeg. Il amène le mixage à -16 LUFS / -1 dBTP par un gain commun à toutes les pistes, et donne les volumes avant et après dans le fichier de montage.

**Architecture :** le nouveau paquet `sound/` fait trois choses :
- `denoise.py` : un protocole `Denoiser` et le moteur DeepFilterNet, en flux par tranches ;
- `filters.py` : la chaîne de filtres ffmpeg ;
- `loudness.py` : les mesures ffmpeg `ebur128` et le gain commun.

`pipeline.run` traite chaque voix vers un WAV float temporaire, qui devient la source de l'écriture du M3. Il mesure la somme et passe `gain_db` à `write_edit`. Tout le reste du M3 ne change pas : analyse, porte, coupes, marqueurs.

**Outils :** ceux du M3, plus `deepfilternet` 0.5.6, `torch` 2.0.1, `torchaudio` 2.0.2, `scipy` ; Python 3.11 seulement.

**Spec :** [conception du M4](../specs/2026-11-28-m4-studio-sound-design.fr.md) · [`docs/spec.fr.md`](../../spec.fr.md) (fait foi)

## Contraintes globales

- Les contraintes du M1 au M3 restent valables (plateformes, `pathlib`, UTF-8, anglais dans le code et les sorties, commits et docs dans les deux langues, jamais une piste pleine résolution entière en mémoire, tests rapides sans modèle ni réseau, ffmpeg permis).
- `requires-python = ">=3.11,<3.12"` ; matrice de la CI : macOS et Windows, Python 3.11 seulement.
- Dépendances ajoutées : `"deepfilternet==0.5.6"`, `"torch==2.0.1"`, `"torchaudio==2.0.2"`, `"scipy"` ; `uv lock`.
- Filtres ffmpeg par défaut, à reprendre tels quels : `highpass=f=100,lowshelf=f=250:g=-4,equalizer=f=500:t=q:w=1:g=-1.5,equalizer=f=2500:t=q:w=1:g=-1,highshelf=f=4500:g=-7,acompressor=threshold=-26dB:ratio=3:attack=10:release=250:makeup=2`.
- DeepFilterNet tourne sur une copie mono à 48 kHz, par tranches de 30 s avec 1 s de recouvrement et un fondu linéaire de 0,5 s dans le recouvrement. Le résultat est remis à la fréquence et au nombre de canaux de la source (mono copié sur chaque canal).
- La piste film n'est jamais traitée. Les analyses restent sur l'audio original. `--dry-run` ne traite aucun son.
- Un seul gain pour toutes les pistes écrites et le mixage : `gain = target_lufs - I(somme)`, ramené pour que `TP(somme) + gain ≤ true_peak_db`.
- Les fichiers temporaires du son sont dans le dossier de sortie, nommés `.<nom>.<slug>.sound.tmp.wav`, en float 32 bits. Ils sont supprimés à la fin, et aussi après une erreur.

## Points à surveiller en revue

1. **Premier passage sans réseau.** Le modèle DeepFilterNet ne peut pas se télécharger : `Error: Could not load the DeepFilterNet model: …`, code de sortie 2, pas de trace Python. Test à la tâche 2.
2. **Une piste de 2 h.** La mémoire reste bornée : une tranche et son recouvrement à la fois. Les raccords entre tranches sont inaudibles : ni clic ni creux de niveau au fondu. Test à la tâche 2 (raccord d'un son continu).
3. **Une piste silencieuse ou presque** (une voix qui ne parle jamais) : pas de gain infini, pas de plantage ; le gain vaut 0 dB et le rapport le dit. Test à la tâche 3.
4. **Bruts en entiers** (PCM 24 bits) : le temporaire traité est en float, et la piste écrite garde le sous-type du brut. Test à la tâche 5.
5. **Une erreur au milieu du traitement du son** : aucun `.sound.tmp.wav` ne reste, et les sorties d'avant restent intactes. Test à la tâche 5.

---

### Tâche 1 : Python 3.11, dépendances, réglages `[sound]`

**Fichiers :** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces :** nouveaux champs de `Settings`, dans une section `[sound]` juste après `[gate]` :

| Champ | Défaut | TOML | Commentaire du modèle |
| --- | --- | --- | --- |
| `sound_enabled: bool` | `True` | `[sound] enabled` | Process the sound of each voice (noise, reverb, EQ, loudness). |
| `sound_denoise: bool` | `True` | `[sound] denoise` | Remove noise and reverb with DeepFilterNet before the filters. |
| `sound_filters: str` | la chaîne par défaut | `[sound] filters` | ffmpeg filters applied to each voice, after the denoiser. |
| `sound_target_lufs: float` | `-16.0` | `[sound] target_lufs` | Loudness of the mix (LUFS). |
| `sound_true_peak_db: float` | `-1.0` | `[sound] true_peak_db` | Highest true peak of the mix (dBTP). |

- [ ] Tests qui échouent : `test_sound_settings_read_from_toml` (`[sound] enabled = false`, `target_lufs = -18` → `False`, `-18.0`) ; l'aller-retour du modèle tient toujours.
- [ ] Fixer Python, ajouter les dépendances, matrice de la CI à `python: ["3.11"]`, `uv lock`, `uv sync` ; la suite complète passe.
- [ ] Commit `build(sound): DeepFilterNet and the [sound] settings, Python 3.11 only / DeepFilterNet et les réglages [sound], Python 3.11 seulement`.

### Tâche 2 : le débruiteur

**Fichiers :** créer `src/podcleaner_editor/sound/__init__.py`, `sound/denoise.py`, `tests/test_denoise.py`

**Interfaces :**
- `class Denoiser(Protocol): name: str; rate: int; def __call__(self, mono: np.ndarray) -> np.ndarray` (float32 à `rate`, même longueur).
- `make_denoiser() -> Denoiser` : DeepFilterNet 3, `rate = 48000`, `name = "DeepFilterNet 3"`. Il importe `df` et charge le modèle au premier appel seulement. Toute exception à l'import ou au chargement lève `EditorError(f"Could not load the DeepFilterNet model: {exc}")`.
- `denoise_file(source: Path, target: Path, denoiser: Denoiser, *, slice_s: float = 30.0, overlap_s: float = 1.0) -> None`. La fonction lit `source` avec `soundfile` tranche par tranche, fait la moyenne en mono, et rééchantillonne à `denoiser.rate` avec `scipy.signal.resample_poly`, avec une marge pour que les bords n'aient pas d'artefacts. Elle applique le débruiteur, fait un fondu linéaire sur les 0,5 s au milieu de chaque recouvrement, rééchantillonne au retour et écrit `target` en FLOAT, à la fréquence et au nombre de canaux de la source. La sortie a exactement autant d'échantillons que la source.

- [ ] Tests qui échouent :
  - `test_identity_denoiser_keeps_the_audio` : un faux qui renvoie son entrée ; un bruit stéréo de 70 s à 44,1 kHz donne une sortie égale à la moyenne mono à 1e-3 près, avec les mêmes échantillons et canaux.
  - `test_slices_join_without_a_dip` : un faux qui multiplie par 0,5 et un son continu à 1 kHz ; le RMS de chaque trame de 10 ms reste à ±0,2 dB de la médiane.
  - `test_denoiser_sees_its_own_rate` : un faux avec `rate = 48000` note la longueur des tableaux reçus ; leur total correspond à 48 kHz.
  - `test_model_load_failure_is_an_editor_error` : l'import de `df` remplacé par un `OSError("offline")` → `EditorError("Could not load the DeepFilterNet model: offline")`.
  - Un test lent `test_deepfilternet_lowers_noise` : bruit blanc plus un son au début de `pedit-full-piste-1-julien.wav`, le bruit de fond plus bas après traitement.
- [ ] Mettre en œuvre ; la suite complète passe ; commit `feat(sound): remove noise and reverb with DeepFilterNet, slice by slice / retirer bruit et réverb avec DeepFilterNet, tranche par tranche`.

### Tâche 3 : filtres et volume

**Fichiers :** créer `sound/filters.py`, `sound/loudness.py`, `tests/test_sound_filters.py`, `tests/test_loudness.py`

**Interfaces :**
- `apply_filters(source: Path, target: Path, filters: str) -> None` : `ffmpeg -af <filters> -c:a pcm_f32le`. Un `filters` vide copie l'audio. En cas d'échec, `EditorError(f"ffmpeg could not apply the sound filters: {stderr}")`.
- `@dataclass(frozen=True) class Loudness: lufs: float; true_peak_db: float`.
- `measure(paths: list[Path]) -> Loudness` : avec un chemin, mesure ce fichier ; avec plusieurs, mesure leur somme (`amix=inputs=n:normalize=0`). Elle utilise `ebur128=peak=true` et lit `I:` et `Peak:` dans le Summary. Le silence (`-inf` ou moins de -70) donne `lufs = -70.0`.
- `shared_gain(loudness: Loudness, target_lufs: float, true_peak_db: float) -> tuple[float, bool]` : le gain en dB, et s'il a été ramené à cause du true peak. Le silence (`lufs <= -70`) donne `(0.0, False)`.

- [ ] Tests qui échouent :
  - `measure` sur un sinus à 1 kHz à -20 dBFS (10 s) : -23 ± 0,5 LUFS (sinus d'amplitude 0,1), true peak -20 ± 0,5.
  - La somme de deux de ces sinus en phase fait +6 dB.
  - `shared_gain(Loudness(-20, -6), -16, -1) == (4.0, False)` ; `shared_gain(Loudness(-20, -3), -16, -1) == (2.0, True)` ; silence → `(0.0, False)`.
  - `apply_filters` avec `volume=-6dB` divise l'amplitude par deux ; avec `""` l'audio ne change pas ; un filtre faux → `EditorError`.
- [ ] Mettre en œuvre ; la suite complète passe ; commit `feat(sound): ffmpeg filters, loudness and the shared gain / filtres ffmpeg, volume et gain commun`.

### Tâche 4 : gain dans l'écriture

**Fichiers :** `src/podcleaner_editor/render/writer.py`, `tests/test_writer.py`

**Interfaces :** `write_edit(..., gain_db: float = 0.0)`. La sortie de chaque piste et le mixage sont multipliés par `10 ** (gain_db / 20)`, après la porte et les fondus et avant l'écrêtage des entiers. Le mixage reste la somme des pistes écrites.

- [ ] Tests qui échouent :
  - `test_gain_applies_to_tracks_and_mix` : +6,0206 dB double chaque piste et le mixage.
  - `test_mix_stays_the_sum_with_gain`.
- [ ] Mettre en œuvre ; la suite complète passe ; commit `feat(render): one gain for every track and the mix / un seul gain pour toutes les pistes et le mixage`.

### Tâche 5 : le son dans la chaîne, le fichier de montage, la CLI

**Fichiers :** `src/podcleaner_editor/pipeline.py`, `src/podcleaner_editor/report/markdown.py`, tests

**Interfaces :**
- `@dataclass(frozen=True) class SoundInfo: chain: str; gain_db: float; capped: bool; rows: tuple[tuple[str, Loudness, Loudness], ...]`. `chain` vaut `"DeepFilterNet 3 + filters"` ou `"filters only"`. Chaque ligne donne (nom du fichier, volume de sa source brute, volume du fichier écrit) ; le « avant » du mixage est la somme brute.
- `AnalysisResult.sound: SoundInfo | None = None`.
- `run(..., denoiser: Denoiser | None = None)` : les tests passent un faux ; sinon `make_denoiser()`, seulement quand `sound_enabled` et `sound_denoise` sont vrais. Sans `dry_run` et avec `sound_enabled`, après `check_renderable` et l'analyse :
  1. pour chaque voix, progression `"Processing the sound of <label>…"` (la première ajoute `" (the DeepFilterNet model is downloaded on first use)"`), puis `denoise_file` (quand `sound_denoise`) et `apply_filters` vers le temporaire ;
  2. progression `"Measuring the loudness…"`, puis `shared_gain(measure([*voix traitées, film]), …)` ;
  3. `write_edit` à partir des voix traitées (film brut), avec `gain_db` ;
  4. mesure de chaque fichier écrit, puis `SoundInfo`.
  Les temporaires sont supprimés dans un `finally`. La vérification de place les compte : la taille des voix traitées s'ajoute à l'estimation de l'écriture. La vérifier dans `run` avant le traitement, avec le même message que l'écriture.
- Fichier de montage : une section `### Sound` après Tracks.
  - Essai : `None: dry run, no audio written.` ; son coupé : `Not processed: [sound] enabled = false.`
  - Sinon : `"<chain> · gain {gain:+.1f} dB · target {target:.1f} LUFS."`, suivi de `" Target not reached: true peak held at {tp:.1f} dBTP."` quand le gain a été ramené.
  - Puis un tableau `| File | Before | After |`, avec des cases `"{lufs:.1f} LUFS / {tp:.1f} dBTP"`.

- [ ] Tests qui échouent (faux débruiteur, petits WAV) :
  - `test_run_processes_the_voices_not_the_film` ;
  - `test_mix_reaches_the_target_loudness` (-16 ± 0,5) ;
  - `test_gain_capped_by_true_peak` ;
  - `test_sound_disabled_writes_raw_levels` ;
  - `test_sound_section_in_edit_file` ;
  - `test_no_sound_tmp_left_after_an_error` (`apply_filters` qui lève une erreur) ;
  - `test_dry_run_processes_no_sound` (le débruiteur n'est jamais appelé) ;
  - `test_pcm24_source_keeps_its_subtype`.
- [ ] Mettre en œuvre ; suite complète ; commit `feat(pipeline): studio sound before the edit is written / son studio avant l'écriture du montage`.

### Tâche 6 : enregistrement de test, écoute, documentation

**Fichiers :** `tests/test_pipeline.py`, `docs/spec.md`, `docs/spec.fr.md`, feuille de route (deux langues), `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

- [ ] Test lent `test_pedit_studio_sound` : `run` sur `samples/pedit`.
  - Le mixage est à -16 ± 0,5 LUFS, avec un true peak ≤ -1,0 dBTP.
  - La différence moyenne d'équilibre sur les six bandes 60–8000 Hz (par rapport à 800–2000 Hz) entre le mixage et `pedit-full-ia.mp3` (à partir de 6,4087 s) est ≤ 2,5 dB ; sauté si le mp3 manque.
  - Toutes les pistes écrites ont le même nombre d'échantillons.
- [ ] `uv run pytest -m slow` → SUCCÈS. Passage réel dans `out/pedit` ; noter le temps de traitement.
- [ ] Documentation dans les deux langues :
  - cahier des charges : ligne Son studio (DeepFilterNet + filtres, WPE écarté, Python 3.11) ;
  - feuille de route : ligne M4 ;
  - README : installation désormais sous Python 3.11, téléchargement au premier passage, `[sound]` ;
  - journal : les entrées du M4 ;
  - CLAUDE.md : ligne Son, Python 3.11, commandes.
- [ ] Commit `docs(m4): studio sound in the spec, roadmap, README and changelog / son studio dans le cahier des charges, la feuille de route, le README et le journal`.
- [ ] Écoute par Julien (étape humaine) : pistes et mixage contre `out/m4-preview/pedit-auphonic-same-volume.wav` ; régler `filters` ; noter les valeurs dans « Réglages validés ».
