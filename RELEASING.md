# Releasing

This document describes how Sourceful releases are cut. It is intended for maintainers; users do not need to read it.

## Versioning

Sourceful follows [Semantic Versioning](https://semver.org/):

- **MAJOR** — incompatible API or schema changes that require user action.
- **MINOR** — backwards-compatible features.
- **PATCH** — backwards-compatible bug fixes.

While the project is pre-1.0, MINOR bumps may include breaking changes, but they must be called out in `CHANGELOG.md`.

## Release checklist

1. Open a release PR titled `release: vX.Y.Z`:
   - Update `CHANGELOG.md`: move entries from `## [Unreleased]` into a new `## [X.Y.Z] - YYYY-MM-DD` section.
   - Bump version strings if any (e.g. `package.json`, `pyproject.toml`).
2. Merge the release PR after CI is green.
3. Tag the merge commit on `main`:
   ```
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
4. Create a GitHub Release from the tag, copying the `## [X.Y.Z]` section from `CHANGELOG.md` as the release notes.
5. Verify any release workflows (Docker image publish, etc.) completed successfully.

## Hotfixes

For urgent fixes against the latest release:

1. Branch from the release tag: `git checkout -b hotfix/X.Y.Z+1 vX.Y.Z`.
2. Apply the fix and open a PR back to `main`.
3. After merge, tag a `vX.Y.Z+1` patch release following the checklist above.

Backports to older minor versions are not supported while the project is pre-1.0.

## Changelog conventions

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/). Group entries under:

- `Added` — new features
- `Changed` — changes to existing behavior
- `Deprecated` — soon-to-be-removed features
- `Removed` — features removed in this release
- `Fixed` — bug fixes
- `Security` — vulnerability fixes (also coordinate with `SECURITY.md`)

Each entry is one line and links to the PR or issue when relevant.
