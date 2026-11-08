# nv-vault

Command-line client for a team key vault server. It is a thin wrapper over the server's HTTP API: it stores no keys, only the server URL and a few settings, and keeps your token in the operating system's keyring.

## Install

```bash
uvx --from git+https://github.com/nhthai173/nv-vault-client nv-vault -h     # run without installing
uv tool install git+https://github.com/nhthai173/nv-vault-client           # or install
```

Works on macOS, Linux and Windows. Needs Python 3.9+ and [uv](https://docs.astral.sh/uv/).

## Set up

```bash
nv-vault config set url https://vault.example.com
nv-vault config set source git+https://github.com/nhthai173/nv-vault-client   # where `upgrade` looks
nv-vault login        # asks for your token; stored in Keychain / Credential Manager / Secret Service
nv-vault health
```

Settings, highest priority first: command-line flag, environment variable, profile in the config file, default.

| Setting | Flag | Variable | Default |
|---|---|---|---|
| server URL | `--url` | `NV_VAULT_URL` | none |
| API version | `--api-version` | `NV_VAULT_API_VERSION` | `v1` |
| timeout (s) | `--timeout` | `NV_VAULT_TIMEOUT` | `30` |
| user | | `NV_VAULT_USER` | none |
| install source | `--source` (upgrade) | `NV_VAULT_SOURCE` | none |
| profile | `--profile` | `NV_VAULT_PROFILE` | `default` |
| token | `--token` (avoid) | `NV_VAULT_TOKEN` | OS keyring |

Several servers: `nv-vault --profile backup config set url ...`, `nv-vault --profile backup login`, `nv-vault config use backup`. The config file is `~/.config/nv-vault/config.json` (`%APPDATA%\nv-vault\config.json` on Windows; `NV_VAULT_CONFIG` overrides). It never contains the token. On a machine without a keyring (CI) set `NV_VAULT_TOKEN`.

## Commands

`config`, `login`, `logout`, `health`, `sync`, `trust`, `trust-sign`, `key get|new`, `ek get|put`, `keyblob`, `upgrade`, `skill`. `nv-vault -h` and `nv-vault <command> -h` have the details. Key material is only ever written with `-o FILE`, to a new owner-only file that is never overwritten; without `-o` you see a fingerprint or a public key. Failures print one line (`nv-vault: 403 ...`) and exit 1.

`nv-vault upgrade` updates the client: for `uv tool install` it reinstalls from `source`, under `uvx` it clears uv's cache so the next run fetches the latest.

## Coding agents

A skill for Claude Code, Codex and similar agents ships with the package:

```bash
nv-vault skill install                          # ~/.claude/skills/nv-vault/SKILL.md
nv-vault skill install --dir <agent skills dir>  # any other agent
nv-vault skill print                            # to paste into AGENTS.md
```

It tells the agent never to print key material, never to run `login`, and to ask before any write command.
