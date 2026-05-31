# Security Policy

## Supported Versions

This project is under active development. Security fixes are applied to the
`main` branch. Tagged releases are not yet maintained on a backport basis.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately using GitHub's **[Private Vulnerability Reporting](https://github.com/himanshu-nakrani/document-qa/security/advisories/new)**
feature on this repository.

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept code, requests, or screenshots)
- The affected version, commit SHA, or deployment configuration
- Any suggested mitigation, if known

You can expect:

- An acknowledgment within **5 business days**
- An initial assessment within **10 business days**
- Coordinated disclosure once a fix is available

## Scope

In scope:

- The Next.js frontend and FastAPI backend in this repository
- Default configurations documented in `README.md` and `docs/`

Out of scope:

- Third-party providers (OpenAI, Google, etc.) — report to the provider
- Issues that require physical access to a self-hosted instance
- The `legacy/` Streamlit prototype (unmaintained)

## Responsible Disclosure

We ask researchers to give us a reasonable window to investigate and patch
before publicly disclosing a vulnerability. We are happy to credit reporters
in release notes once a fix has shipped.
