# AGENTS.md

nv-vault: the client for a team key vault server (stdlib plus `keyring`; macOS, Linux, Windows). Public repository.

- **Nothing company-internal goes in this repo or its history**: no hostnames, IPs, tokens, key material, plugin or customer names, and no description of how the server protects keys. Docs and tests use `127.0.0.1`/`example.com` and generic ids.
- Secrets are never printed: key material is written only with `-o`, to a new owner-only file that is never overwritten. Keep that.
- The skill agents read lives in `src/nv_vault/skill/SKILL.md`; update it whenever a command or its safety behaviour changes (`nv-vault skill print` shows the shipped copy).
- Run `uv run --isolated --with pytest pytest` before calling a change done. The API itself is tested in the server repo against this client.
