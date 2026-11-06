# Contribuer

*[English version](CONTRIBUTING.md)*

Merci de ton intérêt pour PodCleaner-editor. Les contributions sont les bienvenues, par pull request.

## Comment une modification entre dans le projet

- Personne ne pousse directement sur `main`. Toute modification passe par une pull request.
- Fais un fork du dépôt (ou une branche si tu as les droits), fais ta modification, puis ouvre une pull request vers `main`.
- Le propriétaire du dépôt relit et approuve chaque pull request avant qu'elle soit fusionnée.
- Les pull requests sont fusionnées en **squash and merge** : le titre de la pull request devient le message du commit sur `main`. Il doit donc suivre la convention ci-dessous.

## Convention de commit

On utilise [Conventional Commits](https://www.conventionalcommits.org/fr/v1.0.0/) :

```
<type>(<portée optionnelle>): <description courte>
```

| Type | À utiliser pour |
| --- | --- |
| `feat` | Une nouvelle fonctionnalité |
| `fix` | Une correction de bug |
| `docs` | La documentation seule |
| `test` | Ajouter ou corriger des tests |
| `refactor` | Un changement de code qui ne corrige rien et n'ajoute rien |
| `perf` | Une amélioration des performances |
| `build` | Le packaging, les dépendances |
| `ci` | L'intégration continue |
| `chore` | Le reste (outillage, entretien) |

Exemples : `feat(silences): shorten long silences to 0.4 s`, `fix(cli): exit with code 2 when ffmpeg is missing`, `docs: translate the roadmap`.

Un changement incompatible ajoute `!` après le type (`feat!: …`) et une ligne de pied `BREAKING CHANGE:`.

Les messages de commit s'écrivent en anglais.

## Noms de branche

`<type>/<description-courte>`, par exemple `feat/film-clip-detection` ou `docs/readme-install`.

## Avant d'ouvrir une pull request

- Les tests passent : `uv run pytest` (et `uv run pytest -m slow` si tu as touché au code des modèles).
- Le lint passe : `uv run ruff check` et `uv run ruff format --check`.
- Tout nouveau comportement arrive avec ses tests, écrits avant le code.
- Le code tourne sur macOS et Windows : utilise `pathlib` et écris les fichiers texte avec `encoding="utf-8"`.

## Documentation

La documentation existe en anglais et en français. L'anglais est la version par défaut (`nom.md`), le français est à côté (`nom.fr.md`). Si tu modifies l'une, mets l'autre à jour dans la même pull request, ou indique dans la pull request que la traduction manque pour que quelqu'un l'ajoute.
