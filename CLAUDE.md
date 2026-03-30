## Workflow

All changes go through pull requests — do not push directly to `main`.

## Releases

Versioning uses `hatch-vcs` (derived from git tags). To release:

1. Merge PRs to `main`
2. Tag: `git tag v<major>.<minor>.<patch>` and push: `git push origin v<tag>`
3. The `Publish to PyPI` GitHub Action (`.github/workflows/publish.yml`) triggers on `v*` tags, builds with `uv build`, and publishes with `uv publish`

## CI

Runs on every PR and push to `main` (`.github/workflows/ci.yml`). Currently builds the package.

## Tools

Use `uv` (not `pip`) for package installation.
