"""nv-vault: client for a team key vault server. Secrets are written to a new private file with -o, never printed."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfg
from .api import ApiError, call


def write_secret(path: Path, text: str) -> None:
    """Create a NEW file readable by the owner only (never overwrites; chmod is a no-op on Windows)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def _mask(hexval: str) -> str:
    return f"{len(hexval) // 2} bytes, sha256 {hashlib.sha256(hexval.encode()).hexdigest()[:8]}"


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("nv-vault")
    except Exception:
        return "unknown"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nv-vault", description=__doc__)
    ap.add_argument("--version", action="version", version=f"nv-vault {_version()}")
    g = ap.add_argument_group("global options (override env and config file)")
    g.add_argument("--profile", help="named server in the config file (default: NV_VAULT_PROFILE or the default profile)")
    g.add_argument("--url"); g.add_argument("--api-version", dest="api_version"); g.add_argument("--timeout")
    g.add_argument("--token", help="prefer `nv-vault login` or NV_VAULT_TOKEN: argv is visible to other users")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("config", help="global settings").add_subparsers(dest="sub", required=True)
    x = c.add_parser("set"); x.add_argument("key", choices=cfg.KEYS); x.add_argument("value")
    x = c.add_parser("unset"); x.add_argument("key", choices=cfg.KEYS)
    x = c.add_parser("get"); x.add_argument("key", nargs="?", choices=cfg.KEYS)
    x = c.add_parser("use", help="make a profile the default"); x.add_argument("name")
    c.add_parser("path", help="print the config file location")

    up = sub.add_parser("upgrade", help="get the latest nv-vault (needs uv); works for `uv tool install` and for uvx")
    up.add_argument("--source", help="install spec, e.g. git+https://github.com/<user>/nv-vault-client (saved with `config set source`)")
    sk = sub.add_parser("skill", help="the bundled skill for coding agents (Claude Code, Codex, ...)").add_subparsers(dest="sub", required=True)
    sk.add_parser("print", help="print SKILL.md")
    x = sk.add_parser("install", help="copy SKILL.md into an agent's skills folder")
    x.add_argument("--dir", type=Path, help="target folder (default: ~/.claude/skills/nv-vault; for Codex pass its skills folder)")
    x.add_argument("--force", action="store_true", help="overwrite an existing SKILL.md")
    sub.add_parser("login", help="store the token for the profile in the OS keyring (prompted, not echoed)")
    sub.add_parser("logout", help="remove the stored token")
    sub.add_parser("health"); sub.add_parser("sync", help="have the server git-pull")
    t = sub.add_parser("trust", help="serial and signed trust store")
    t.add_argument("-o", "--out", type=Path, help="write trusted_vendors.enc here")
    sub.add_parser("trust-sign", help="(write role) bump serial, sign the trust store")
    k = sub.add_parser("key").add_subparsers(dest="sub", required=True)
    x = k.add_parser("get"); x.add_argument("vendor"); x.add_argument("key_id")
    x.add_argument("-o", "--out", type=Path, help="write the PRIVATE key to a new private file; omitted: print the public key only")
    x = k.add_parser("new", help="(write role) generate, or import with --import-file / --public")
    x.add_argument("vendor"); x.add_argument("key_id"); x.add_argument("--name")
    x.add_argument("--import-file", type=Path); x.add_argument("--public")
    e = sub.add_parser("ek").add_subparsers(dest="sub", required=True)
    x = e.add_parser("get"); x.add_argument("plugin"); x.add_argument("version")
    x.add_argument("-o", "--out", type=Path, help="write K_p to a new private file; omitted: print length and fingerprint only")
    x = e.add_parser("put", help="(write role) store K_p from a file")
    x.add_argument("plugin"); x.add_argument("version"); x.add_argument("--kp-file", type=Path, required=True)
    b = sub.add_parser("keyblob", help="mint a per-license key-blob; K_p stays on the server")
    b.add_argument("plugin"); b.add_argument("version")
    m = b.add_mutually_exclusive_group(required=True)
    m.add_argument("--seed-file", type=Path); m.add_argument("--seed", metavar="HEX")
    b.add_argument("-o", "--out", type=Path, required=True)
    return ap


def _config_cmd(a, env) -> None:
    d = cfg.load(env)
    prof = cfg.profile_name(a.profile, env)
    if a.sub == "set":
        d["profiles"].setdefault(prof, {})[a.key] = a.value
        print(f"{prof}.{a.key} = {a.value}  ({cfg.save(d, env)})")
    elif a.sub == "unset":
        d["profiles"].get(prof, {}).pop(a.key, None); cfg.save(d, env); print(f"{prof}.{a.key} removed")
    elif a.sub == "use":
        d["default_profile"] = a.name; cfg.save(d, env); print(f"default profile: {a.name}")
    elif a.sub == "path":
        print(cfg.config_path(env))
    else:
        flags = {k: getattr(a, k, None) for k in cfg.KEYS}
        names = [prof] if a.key is None and prof not in d["profiles"] else sorted(d["profiles"]) or [prof]
        for n in ([prof] if a.key else names):
            eff = {**cfg.DEFAULTS, **d["profiles"].get(n, {})}
            mark = "*" if n == d["default_profile"] else " "
            print(f"{mark} {n}: " + (str(eff.get(a.key)) if a.key else ", ".join(f"{k}={eff[k]}" for k in eff)))


def _uv(*args: str) -> subprocess.CompletedProcess:
    uv = shutil.which("uv")
    if not uv:
        raise cfg.ConfigError("uv not found: install it from https://docs.astral.sh/uv/")
    return subprocess.run([uv, *args], text=True, capture_output=True)


def _upgrade(a, env) -> None:
    src = cfg.setting("source", getattr(a, "source", None), a.profile, env)
    installed = any(line.split()[:1] == ["nv-vault"] for line in _uv("tool", "list").stdout.splitlines())
    if installed:     # `uv tool install`: reinstall from the source, or let uv re-resolve the original one
        r = _uv("tool", "install", "--reinstall", "--force", src) if src else _uv("tool", "upgrade", "nv-vault")
    else:             # uvx runs from its cache: drop it so the next run resolves the newest version
        r = _uv("cache", "clean", "nv-vault")
    if r.returncode != 0:
        raise cfg.ConfigError(f"uv failed: {(r.stderr or r.stdout).strip()[-300:]}")
    again = f'uvx --from "{src}" nv-vault' if src else "uvx --from <source> nv-vault"
    print("nv-vault updated" if installed else f"cache cleared; the next `{again} ...` fetches the latest")
    if not src:
        print("tip: `nv-vault config set source <git+https://...#subdirectory=clients/nv-vault>` so upgrade knows where to look")


def run(a, env=os.environ) -> None:
    if a.cmd == "config":
        return _config_cmd(a, env)
    if a.cmd == "upgrade":
        return _upgrade(a, env)
    if a.cmd == "skill":
        from importlib.resources import files
        text = files("nv_vault").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
        if a.sub == "print":
            print(text, end="")
        else:
            d = a.dir or Path.home() / ".claude" / "skills" / "nv-vault"
            d.mkdir(parents=True, exist_ok=True)
            f = d / "SKILL.md"
            if f.exists() and not a.force:
                raise cfg.ConfigError(f"{f} exists; --force to overwrite")
            f.write_text(text, encoding="utf-8"); print(f)
        return
    prof = cfg.profile_name(a.profile, env)
    if a.cmd == "login":
        tok = getpass.getpass(f"Token for profile {prof!r}: ").strip()
        if not tok:
            raise cfg.ConfigError("empty token")
        cfg.set_token(prof, tok); print(f"token stored in the OS keyring for profile {prof!r}")
        return
    if a.cmd == "logout":
        cfg.delete_token(prof); print("token removed")
        return
    s = cfg.resolve({"url": a.url, "api_version": a.api_version, "timeout": a.timeout}, a.profile, env)
    tok = cfg.get_token(prof, a.token, env)

    def api(method, path, body=None, versioned=True):
        return call(s["url"], s["api_version"], tok, method, path, body, s["timeout"], versioned)

    if a.cmd == "health":
        print(api("GET", "/healthz", versioned=False))
    elif a.cmd == "sync":
        api("POST", "/sync"); print("synced")
    elif a.cmd == "trust":
        r = api("GET", "/trust")
        if a.out:
            if not r["blob_b64"]:
                raise ApiError("the server has no signed trust store yet (run trust-sign)")
            a.out.write_bytes(base64.b64decode(r["blob_b64"]))
        print(f"serial {r['serial']}" + (f" -> {a.out}" if a.out else ""))
    elif a.cmd == "trust-sign":
        print("serial", api("POST", "/trust/sign")["serial"])
    elif a.cmd == "key" and a.sub == "get":
        r = api("GET", f"/keys/{a.vendor}/{a.key_id}")
        if a.out:
            write_secret(a.out, r["private_hex"]); print(a.out)
        else:
            print(r["public_hex"])
    elif a.cmd == "key":
        body = {"name": a.name, "public_hex": a.public,
                "private_hex": a.import_file.read_text().strip() if a.import_file else None}
        print(api("POST", f"/keys/{a.vendor}/{a.key_id}", body)["public_hex"])
    elif a.cmd == "ek" and a.sub == "get":
        kp = api("GET", f"/ek/{a.plugin}/{a.version}")["kp_hex"]
        if a.out:
            write_secret(a.out, kp); print(a.out)
        else:
            print(_mask(kp))
    elif a.cmd == "ek":
        r = api("PUT", f"/ek/{a.plugin}/{a.version}", {"kp_hex": a.kp_file.read_text().strip()})
        print("stored" if r["stored"] else "already stored (same K_p)")
    elif a.cmd == "keyblob":
        seed = a.seed or a.seed_file.read_text().strip()
        r = api("POST", "/keyblob", {"plugin": a.plugin, "version": a.version, "seed_hex": seed})
        write_secret(a.out, r["blob"]); print(a.out)


def main(argv: list[str] | None = None) -> int:
    try:
        run(parser().parse_args(argv))
    except (cfg.ConfigError, ApiError, OSError, ValueError) as e:
        print(f"nv-vault: {e}", file=sys.stderr)
        return 1
    return 0
