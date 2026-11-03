<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Contributing

Want to deposit data? You're in the wrong file, see the [README](README.md).

This is for developers. Work happens on forks: fork, set it up as below, test on your fork, then open a PR.

## Fork setup

Forks start with most of this off, so:

- Settings → General → Features: tick **Issues**
- Actions tab: enable workflows
- Settings → Actions → General → Workflow permissions: **Read and write** (the bot pushes reports)
- Settings → Pages → Source: **GitHub Actions**
- Put yourself in `safe_list.yaml`, otherwise every issue you open gets `rejected`. Your id is the `id` field at `https://api.github.com/users/<your-username>`, just open it in a browser

## Secrets and variables

Settings → Secrets and variables → Actions.

| Name | Kind | What |
|---|---|---|
| `GH_TOKEN` | secret | Your [fine-grained PAT](https://github.com/settings/personal-access-tokens/new), only on the fork, Issues: read & write |
| `ZENODO_SANDBOX` | secret | [Zenodo sandbox token](https://sandbox.zenodo.org/account/settings/applications/tokens/new/), scopes `deposit:write` + `deposit:actions` |
| `ZENODO_PRODUCTION` | secret | Upstream only. Don't set it on a fork |
| `ENVIRONMENT` | variable | Leave it unset. Defaults to `development`, so Zenodo calls go to the sandbox. Upstream has `production` |

Upstream `GH_TOKEN` belongs to the crocibot account, so the bot's comments and labels show up as crocibot. On your fork they show up as you.

## Try it

Open an issue on your fork titled `deposit localhost:330 doi:10.1007/978-3-030-00668-6_8` and paste the example body from the README. Watch the run in Actions, you should get a comment and a `done` label. `localhost` domains are treated as tests and never go to Zenodo, so use those.

## Local

```bash
uv sync --all-extras --dev
uv run python -m unittest discover test/
```

Tests mock all tokens, no secrets needed.

`scripts/run_meta_process.py` (the monthly Meta ingestion) is a different beast: it reads a `.env` in the repo root (`GH_TOKEN`, `GITHUB_REPOSITORY`, ...) plus `meta_config.yaml`, and wants a running triplestore.

## PRs

- Against `main` of `opencitations/crowdsourcing`
- [Conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, ...), semantic-release reads them. `[release]` in the commit message cuts a release
- New files need an SPDX header, the REUSE check will fail otherwise. Suggested licenses: `ISC` for code, `CC-BY-4.0` for docs, `CC0-1.0` for config files
