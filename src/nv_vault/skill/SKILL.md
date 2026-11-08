---
name: nv-vault
description: Use when you need plugin signing keys, plugin content keys (K_p), key-blobs or the signed trust store from the company's nv-vault server, e.g. packing or installing a signed plugin. Wraps the `nv-vault` CLI. Never print or log key material.
---

# nv-vault

`nv-vault` is a command-line client for the team's key vault server. Run it with `uvx --from <source> nv-vault ...` or, if installed, `nv-vault ...`. `nv-vault -h` and `nv-vault <command> -h` list everything.

## Rules for agents

- **Never print, echo, paste or log a key, a K_p, a key-blob or a token.** Key material goes to a file with `-o FILE` (created new, owner-only, never overwrites) and is read from that file by the next command. Delete such files when the task is done.
- **Do not run `nv-vault login`.** It prompts for a token and needs the human. If a command says there is no token, stop and tell the user to run `nv-vault login` (or set `NV_VAULT_TOKEN`).
- **Do not pass `--token` on the command line** and do not write tokens into files, scripts, commits or memory.
- **Ask the user before any write command**: `ek put`, `key new`, `trust-sign`. They change the shared vault for everyone and cannot be undone by editing a file. Read commands need no confirmation.
- `ek get` and `key get` without `-o` only show a fingerprint or the public key. That is enough to check that something exists; do not look for a way around it.
- A `warning: ... may be stale` on stderr means the server could not fetch the latest vault data. Do not sign or pack with a key from a stale answer; tell the user.
- Exit code 0 means success; 1 means failure with a one-line reason on stderr (`401` bad or missing token, `403` the token's role is too low, `404` not found, `409` conflict, e.g. a different K_p already exists for that plugin version: bump the version instead of retrying).

## Common tasks

```bash
nv-vault config get                      # server URL, API version and profile in use (no secrets)
nv-vault health                          # is the server reachable
nv-vault products                        # which products this token can use
nv-vault trust -o trusted_vendors.enc    # the signed trust store; prints its serial
nv-vault ek get PLUGIN VERSION           # does a K_p exist? (fingerprint only)
nv-vault ek get PLUGIN VERSION -o kp.hex # K_p into a file, for `pack --kp "$(cat kp.hex)"`
nv-vault key get VENDOR KEY_ID -o key.hex  # signing key into a file; without -o only the public key
nv-vault keyblob PLUGIN VERSION --seed-file seed.hex -o PLUGIN-VERSION.key   # the server mints it; K_p never leaves the server
nv-vault sync                            # ask the server to pull the latest vault data
nv-vault upgrade                         # update the client itself (needs uv)
```

Keys are grouped by **product** (the short name such as myproduct, e.g. `myproduct`): set it once with `nv-vault config set product <slug>` or pass `--product`. `nv-vault products` lists the ones your token can use. Global options come before the command: `--profile`, `--url`, `--product`, `--api-version`, `--timeout`. They can also be set once with `nv-vault config set KEY VALUE` or the `NV_VAULT_*` environment variables.
