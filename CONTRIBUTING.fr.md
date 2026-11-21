# Contribuer

**Français** · [English](CONTRIBUTING.md)

## Fonctionnement

- `main` est protégée : personne n'y pousse directement, et le force-push et la suppression sont bloqués.
- Toute modification passe par une pull request. Une PR n'est fusionnée qu'après l'approbation du mainteneur (voir [CODEOWNERS](.github/CODEOWNERS)).
- Travaille sur une branche nommée d'après son type : `feat/silence-detection`, `fix/track-loading`, `docs/readme`.

## Messages de commit

Les commits suivent [Conventional Commits](https://www.conventionalcommits.org/fr/), écrits **en anglais puis en français**, pour que tout le monde puisse lire l'historique :

```
<type>(<portée optionnelle>): <English summary> / <résumé en français>
```

Un corps facultatif contient un paragraphe en anglais, une ligne vide, puis le même paragraphe en français.

Types : `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`. Un changement incompatible ajoute `!` après le type (`feat!: …`) ou un pied de page `BREAKING CHANGE:`.

Exemples :

```
feat(silences): shorten long silences to 0.4 s / raccourcir les longs blancs à 0,4 s
fix(cli): exit with code 2 when ffmpeg is missing / sortir avec le code 2 quand ffmpeg manque
docs: translate the roadmap / traduire la feuille de route
```

## Titre et description de pull request

- Le **titre** suit le même format qu'un titre de commit : `type: English / français`.
- La **description** est écrite entièrement en anglais d'abord, puis entièrement en français, séparées par `---`.
- Chaque langue commence par un **TL;DR** : 1 à 3 phrases simples qui disent ce que change la PR et pourquoi, compréhensibles sans lire le code.

Le [modèle de PR](.github/pull_request_template.md) se remplit tout seul à l'ouverture d'une PR.

## Code

Tout ce qui est dans le code est en anglais : identifiants, commentaires, docstrings, messages d'assertion, commentaires des fichiers de configuration. Les sorties du programme sont aussi en anglais : messages, erreurs, aide de la CLI, logs, fichier de montage et clés de la configuration.

Le code tourne sur macOS et Windows : utilise `pathlib`, jamais de chemin en dur, et écris les fichiers texte avec `encoding="utf-8"`.

## Documentation

La documentation existe en anglais et en français. Les fichiers anglais n'ont pas de suffixe (`README.md`), les fichiers français finissent par `.fr.md` (`README.fr.md`). Si tu modifies l'un, mets l'autre à jour dans la même PR, ou indique dans la PR que la traduction est à faire. Le cahier des charges a été écrit en français : [`docs/spec.fr.md`](docs/spec.fr.md) fait foi, [`docs/spec.md`](docs/spec.md) en est la traduction.

## Avant d'ouvrir une PR

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```

Tout doit passer sur macOS et Windows ; la CI vérifie les deux. Tout nouveau comportement arrive avec ses tests, écrits avant le code.
