"""Local Metabase API client shared by dashboard setup and reconciliation."""

import json
import os
from pathlib import Path
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class Metabase:
    def __init__(self):
        self.url = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
        self.session = None

    def request(self, method, path, data=None):
        headers = {"Content-Type": "application/json"}
        if self.session:
            headers["X-Metabase-Session"] = self.session
        request = Request(self.url + "/api" + path, method=method, headers=headers,
                          data=None if data is None else json.dumps(data).encode("utf-8"))
        try:
            with urlopen(request, timeout=120) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as exc:
            raise RuntimeError(f"Metabase {method} {path}: HTTP {exc.code}: "
                               + exc.read().decode("utf-8", errors="replace")) from exc

    def login(self, allow_setup=False):
        credentials_path = ROOT / "data/metabase_local.json"
        credentials = {}
        if credentials_path.is_file():
            credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        if os.environ.get("METABASE_USER"):
            credentials = {"username": os.environ["METABASE_USER"],
                           "password": os.environ["METABASE_PASSWORD"]}
        properties = self.request("GET", "/session/properties")
        token = properties.get("setup-token")
        if token and not properties.get("has-user-setup") and allow_setup:
            if not credentials:
                credentials = {"username": "olap@example.test", "password": secrets.token_urlsafe(24) + "A1!"}
            # Save before setup so the new administrator's password cannot be lost.
            credentials_path.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
            self.request("POST", "/setup", {
                "token": token,
                "user": {"email": credentials["username"], "password": credentials["password"],
                         "first_name": "OLAP", "last_name": "Admin"},
                "prefs": {"site_name": "Бронирования H1/H2", "allow_tracking": False},
            })
        if not credentials:
            raise RuntimeError("Set METABASE_USER and METABASE_PASSWORD for the existing Metabase account")
        self.session = self.request("POST", "/session", credentials)["id"]
        return self
