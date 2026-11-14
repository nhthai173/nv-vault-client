import io
import json

from nv_vault import api


def test_every_request_says_which_client_version_sent_it(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return Resp(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api.call("http://127.0.0.1:1", "v1", "t", "GET", "/healthz") == {"ok": True}
    assert seen["ua"] == api.USER_AGENT and seen["ua"].startswith("nv-vault/")
