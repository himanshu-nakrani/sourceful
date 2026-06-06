# Project Governance

Sourceful is an open-source project under the Apache License 2.0. This document describes how decisions are made, who can make them, and how new contributors can earn trust over time. It is intentionally lightweight: the project is small, and governance should grow only as fast as the community does.

## Roles

### Users

Anyone running Sourceful, filing issues, or asking questions. Users have no formal responsibilities — feedback, bug reports, and use cases are welcome.

### Contributors

Anyone who has had a pull request, issue, or documentation change accepted. Contributors do not need ongoing commitment; one good change is enough.

### Maintainers

Maintainers have write access to the repository and can review, merge, and release. They are responsible for:

- Reviewing pull requests in a timely manner.
- Triaging issues and labelling them.
- Cutting releases per [RELEASING.md](RELEASING.md).
- Upholding the [Code of Conduct](CODE_OF_CONDUCT.md).
- Mentoring new contributors.

The current maintainer list lives in [MAINTAINERS.md](MAINTAINERS.md).

### Project Lead

One maintainer holds the final tie-breaking vote on disagreements that cannot be resolved by discussion. The project lead is also the point of contact for security disclosures, trademark questions, and any legal matters. The current project lead is identified in [MAINTAINERS.md](MAINTAINERS.md).

## Becoming a Maintainer

A contributor may be invited to become a maintainer when they have:

1. Landed multiple non-trivial pull requests over at least a few weeks.
2. Demonstrated good judgment in reviews and discussions.
3. Shown willingness to help others (answering issues, reviewing PRs, improving docs).

Any existing maintainer may nominate a candidate by opening a private discussion with the other maintainers. A nomination passes with **lazy consensus** (no objection within 7 days) or a simple majority of existing maintainers if there are objections.

A maintainer may step down at any time by opening a PR removing themselves from `MAINTAINERS.md`. A maintainer who has been inactive for 6 months without notice may be moved to "emeritus" status by the remaining maintainers.

## Decision Making

The project uses **lazy consensus**. Most changes are merged when a maintainer approves them and CI passes. Larger decisions follow this escalation:

1. **Routine changes** (bug fixes, docs, small features) — one maintainer approval is enough.
2. **Substantive changes** (new dependencies, breaking API changes, architectural shifts) — open an issue or discussion first, wait at least 72 hours for input, and require approval from a maintainer who is not the author.
3. **Disputed changes** — if maintainers disagree, the project lead decides after discussion. This should be rare.

Anyone may propose a change. Maintainer status confers review and merge rights, not exclusive proposal rights.

## Releases

Releases are cut from `main` and tagged `vX.Y.Z` following [Semantic Versioning](https://semver.org/). The release process and changelog conventions are documented in [RELEASING.md](RELEASING.md).

## Changes to Governance

This document may be amended by pull request. Changes follow the same "substantive changes" rule above: open a discussion, wait at least 72 hours, require approval from a maintainer who is not the author.

## Code of Conduct

All participants — users, contributors, maintainers — are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Reports go to the project lead listed in `MAINTAINERS.md`.
