import pytest

from nv_vault import cli, config as cfg


class FakeKeyring:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        self.d.pop((s, u))


@pytest.fixture
def env(tmp_path, monkeypatch):
    kr = FakeKeyring()
    monkeypatch.setattr(cfg, "_keyring", lambda: kr)
    for k in ("NV_VAULT_URL", "NV_VAULT_USER", "NV_VAULT_API_VERSION", "NV_VAULT_TIMEOUT", "NV_VAULT_TOKEN", "NV_VAULT_PROFILE", "NV_VAULT_PRODUCT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NV_VAULT_CONFIG", str(tmp_path / "c.json"))
    return kr


def test_precedence_flag_env_profile_default(env, monkeypatch):
    with pytest.raises(cfg.ConfigError, match="no server URL"):
        cfg.resolve({})
    assert cli.main(["config", "set", "url", "http://file:1/"]) == 0
    assert cfg.resolve({}) == {"url": "http://file:1", "user": None, "api_version": "v1", "timeout": 30.0, "source": None, "product": None}
    monkeypatch.setenv("NV_VAULT_URL", "http://env:2")
    assert cfg.resolve({})["url"] == "http://env:2"
    assert cfg.resolve({"url": "http://flag:3"})["url"] == "http://flag:3"
    assert cli.main(["config", "set", "api_version", "v2"]) == 0
    assert cfg.resolve({})["api_version"] == "v2"
    assert cli.main(["config", "set", "timeout", "abc"]) == 0
    with pytest.raises(cfg.ConfigError, match="timeout"):
        cfg.resolve({})


def test_profiles_are_separate_and_default_switches(env):
    cli.main(["--profile", "main", "config", "set", "url", "http://main"])
    cli.main(["--profile", "fallback", "config", "set", "url", "http://fb"])
    cli.main(["config", "use", "fallback"])
    assert cfg.resolve({})["url"] == "http://fb"
    assert cfg.resolve({}, "main")["url"] == "http://main"
    cli.main(["--profile", "main", "config", "unset", "url"])
    with pytest.raises(cfg.ConfigError):
        cfg.resolve({}, "main")


def test_token_from_flag_env_keyring_and_never_in_the_file(env, monkeypatch, tmp_path):
    with pytest.raises(cfg.ConfigError, match="nv-vault login"):
        cfg.get_token("default")
    monkeypatch.setattr("getpass.getpass", lambda *_: " secret-token ")
    assert cli.main(["login"]) == 0
    assert cfg.get_token("default") == "secret-token"                     # stripped, stored per profile
    assert cfg.get_token("other", env={"NV_VAULT_TOKEN": "from-env"}) == "from-env"
    assert cfg.get_token("default", flag="from-flag") == "from-flag"
    assert cfg.get_token("default", env={"NV_VAULT_TOKEN": "e"}, flag=None) == "e"
    cli.main(["config", "set", "url", "http://x"])
    assert "secret-token" not in (tmp_path / "c.json").read_text()
    assert cli.main(["logout"]) == 0
    with pytest.raises(cfg.ConfigError):
        cfg.get_token("default")


def test_keyring_failure_points_to_env(env, monkeypatch):
    def boom():
        class K:
            def get_password(self, *a): raise RuntimeError("no backend")
        return K()
    monkeypatch.setattr(cfg, "_keyring", boom)
    with pytest.raises(cfg.ConfigError, match="NV_VAULT_TOKEN"):
        cfg.get_token("default")


def test_config_path_follows_the_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("NV_VAULT_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "x"))
    monkeypatch.setattr(cfg, "_is_windows", lambda: False)
    assert cfg.config_path() == tmp_path / "x" / "nv-vault" / "config.json"
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    monkeypatch.setattr(cfg, "_is_windows", lambda: True)
    assert cfg.config_path() == tmp_path / "ad" / "nv-vault" / "config.json"


def test_write_secret_never_overwrites(tmp_path):
    f = tmp_path / "s"
    cli.write_secret(f, "one")
    with pytest.raises(FileExistsError):
        cli.write_secret(f, "two")
    assert f.read_text() == "one"


def test_upgrade_picks_the_uv_command(env, monkeypatch, capsys):
    calls = []

    def fake_uv(*args):
        calls.append(args)
        out = "nv-vault v0.1.0\n- nv-vault\n" if args[:2] == ("tool", "list") and fake_uv.installed else ""
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()
    monkeypatch.setattr(cli, "_uv", fake_uv)
    fake_uv.installed = True
    assert cli.main(["upgrade"]) == 0                                    # installed as a tool, no source known
    assert calls[-1] == ("tool", "upgrade", "nv-vault")
    assert cli.main(["config", "set", "source", "git+https://h/r#subdirectory=clients/nv-vault"]) == 0
    assert cli.main(["upgrade"]) == 0                                    # source from the config file
    assert calls[-1] == ("tool", "install", "--reinstall", "--force", "git+https://h/r#subdirectory=clients/nv-vault")
    fake_uv.installed = False                                            # running under uvx
    assert cli.main(["upgrade"]) == 0
    assert calls[-1] == ("cache", "clean", "nv-vault") and "fetches the latest" in capsys.readouterr().out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0 and "nv-vault" in capsys.readouterr().out


def test_skill_ships_and_installs(tmp_path, capsys):
    assert cli.main(["skill", "print"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("---\nname: nv-vault\n") and "Never print" in out
    d = tmp_path / "skills" / "nv-vault"
    assert cli.main(["skill", "install", "--dir", str(d)]) == 0
    assert (d / "SKILL.md").read_text(encoding="utf-8") == out
    assert cli.main(["skill", "install", "--dir", str(d)]) == 1          # no silent overwrite
    assert cli.main(["skill", "install", "--dir", str(d), "--force"]) == 0


def test_product_is_required_for_key_commands(env, monkeypatch, capsys):
    monkeypatch.setenv("NV_VAULT_TOKEN", "t"); monkeypatch.setenv("NV_VAULT_URL", "http://127.0.0.1:9")
    assert cli.main(["ek", "get", "p", "1"]) == 1
    assert "no product" in capsys.readouterr().err
    assert cli.main(["config", "set", "product", "myproduct"]) == 0
    assert cfg.resolve({})["product"] == "myproduct"
    assert cfg.resolve({"product": "other-product"})["product"] == "other-product"
