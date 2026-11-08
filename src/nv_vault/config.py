"""Settings: flag > environment > profile in the config file > default. The token is never in the file."""
from __future__ import annotations

import json
import os
from pathlib import Path

KEYRING_SERVICE = "nv-vault"
DEFAULTS = {"api_version": "v1", "timeout": "30"}
KEYS = ("url", "user", "api_version", "timeout", "source", "product")     # `config set` accepts these; source = where `upgrade` installs from
ENV = {"url": "NV_VAULT_URL", "user": "NV_VAULT_USER", "api_version": "NV_VAULT_API_VERSION", "timeout": "NV_VAULT_TIMEOUT", "source": "NV_VAULT_SOURCE", "product": "NV_VAULT_PRODUCT"}


class ConfigError(Exception):
    pass


def _is_windows() -> bool:
    return os.name == "nt"


def config_path(env=os.environ) -> Path:
    if env.get("NV_VAULT_CONFIG"):
        return Path(env["NV_VAULT_CONFIG"])
    if _is_windows():
        base = Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "nv-vault" / "config.json"


def load(env=os.environ) -> dict:
    try:
        d = json.loads(config_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("default_profile", "default")
    d.setdefault("profiles", {})
    return d


def save(d: dict, env=os.environ) -> Path:
    p = config_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return p


def profile_name(flag: str | None, env=os.environ) -> str:
    return flag or env.get("NV_VAULT_PROFILE") or load(env)["default_profile"]


def setting(key: str, flag: str | None = None, profile: str | None = None, env=os.environ) -> str | None:
    """One setting by the usual precedence, without requiring the others (used by `upgrade`)."""
    prof = load(env)["profiles"].get(profile_name(profile, env), {})
    return flag or env.get(ENV[key]) or prof.get(key) or DEFAULTS.get(key)


def resolve(flags: dict, profile: str | None = None, env=os.environ) -> dict:
    """The effective url / user / api_version / timeout."""
    prof = load(env)["profiles"].get(profile_name(profile, env), {})
    out = {}
    for k in KEYS:
        out[k] = flags.get(k) or env.get(ENV[k]) or prof.get(k) or DEFAULTS.get(k)
    if not out["url"]:
        raise ConfigError("no server URL: `nv-vault config set url http://host:8095`, or --url / NV_VAULT_URL")
    out["url"] = out["url"].rstrip("/")
    if out["product"] is not None and not out["product"].strip():
        out["product"] = None
    try:
        out["timeout"] = float(out["timeout"])
    except ValueError:
        raise ConfigError(f"timeout must be a number, got {out['timeout']!r}") from None
    return out


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        raise ConfigError("the keyring package is missing: pip install keyring, or use NV_VAULT_TOKEN") from None


def get_token(profile: str, flag: str | None = None, env=os.environ) -> str:
    tok = flag or env.get("NV_VAULT_TOKEN")
    if tok:
        return tok
    try:
        tok = _keyring().get_password(KEYRING_SERVICE, profile)
    except ConfigError:
        raise
    except Exception as e:      # no backend on a headless box
        raise ConfigError(f"cannot read the OS keyring ({e.__class__.__name__}): set NV_VAULT_TOKEN instead") from None
    if not tok:
        raise ConfigError(f"no token for profile {profile!r}: run `nv-vault login`, or set NV_VAULT_TOKEN")
    return tok


def set_token(profile: str, token: str) -> None:
    try:
        _keyring().set_password(KEYRING_SERVICE, profile, token)
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"cannot write the OS keyring ({e.__class__.__name__}): use NV_VAULT_TOKEN instead") from None


def delete_token(profile: str) -> None:
    try:
        _keyring().delete_password(KEYRING_SERVICE, profile)
    except ConfigError:
        raise
    except Exception:
        pass
