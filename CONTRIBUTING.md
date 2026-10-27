# Contributing

Thanks for helping improve ZIP-to-Workspace.

## Before opening an issue

- Search existing issues.
- Use a small, non-sensitive test archive.
- Include reproduction steps, expected and actual behavior, OS, Chrome version, Python version, and relevant error text.
- Never attach credentials, private code, or confidential ZIP archives.

## Development setup

Requirements: Python 3.10+, Node.js for JavaScript syntax checks, and Google Chrome for end-to-end testing.

Run tests:

```bash
python -m unittest discover -s tests -v
node --check extension/service-worker.js
node --check extension/popup.js
```

## Pull requests

- Keep changes focused and explain why they are needed.
- Add regression tests for bugs.
- Do not add automatic code execution, dependency installation, or network uploads without prior discussion and explicit documentation.
- Do not broaden extension permissions without explaining why.
- Update README, privacy, security, and changelog documentation when behavior changes.
- Never commit secrets, local configuration, test downloads, generated workspaces, or personal paths.

Do not open public issues for exploitable security vulnerabilities. Follow `SECURITY.md`.
