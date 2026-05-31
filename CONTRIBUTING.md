# Contributing to document-qa

Thanks for your interest in contributing! This project is an open, self-hostable RAG application built with Next.js and FastAPI. Contributions of all kinds — bug reports, fixes, features, docs — are welcome.

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it.

## Getting started

1. Fork the repo and clone your fork.
2. See `README.md` for installation and local setup.
3. Copy `.env.example` to `.env` and fill in the values you need.
4. Frontend: `npm ci` then `npm run dev`.
5. Backend: `python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`, then run `uvicorn backend.main:app --reload` and `python -m backend.worker` in separate terminals.

`AGENTS.md` documents the project layout, run commands, and testing expectations in detail.

## Workflow

1. Open an issue first for non-trivial changes so the approach can be discussed.
2. Create a branch from `main`.
3. Keep changes scoped — bug fixes and features should not bundle unrelated refactors.
4. Add or update tests where it makes sense.
5. Run `npm run lint`, `npm run build`, and `pytest -q backend/tests` before opening a PR.
6. Open a pull request against `main` using the PR template.

## Commit messages

- Use clear, present-tense subjects.
- Reference issues with `Fixes #123` or `Refs #123` when applicable.

## Reporting bugs

Use the GitHub issue tracker and follow the bug-report template. Please include:

- What you did
- What you expected
- What happened instead
- Environment (OS, Node version, Python version, deployment mode)

## Security

Do **not** open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the disclosure process.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
