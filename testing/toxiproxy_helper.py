"""
Helper for controlling Toxiproxy via its HTTP API.

Toxiproxy simulates network failures (WiFi drop, latency, etc.) by proxying
TCP connections and injecting "toxics".

Requires Toxiproxy running locally:
    toxiproxy-server
"""
from __future__ import annotations

import os

import requests

TOXIPROXY_API = os.environ.get("TOXIPROXY_API", "http://localhost:8474")


class ToxiproxyError(RuntimeError):
    pass


def _request(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{TOXIPROXY_API}{path}"
    try:
        response = requests.request(method, url, timeout=5, **kwargs)
    except requests.RequestException as exc:
        raise ToxiproxyError(f"Cannot reach Toxiproxy at {TOXIPROXY_API}") from exc
    return response


def is_toxiproxy_running() -> bool:
    try:
        response = _request("GET", "/version")
        return response.status_code == 200
    except ToxiproxyError:
        return False


def _proxy_names(payload) -> list[str]:
    """Toxiproxy v2 returns a name→proxy map; older builds return a list."""
    if isinstance(payload, dict):
        return list(payload.keys())
    if isinstance(payload, list):
        return [proxy["name"] for proxy in payload]
    return []


def ensure_proxy(name: str, listen: str, upstream: str) -> None:
    """Create proxy if missing; reset if it already exists."""
    response = _request("GET", "/proxies")
    if response.status_code != 200:
        raise ToxiproxyError(f"Failed to list proxies: {response.text}")

    if name in _proxy_names(response.json()):
        _request("DELETE", f"/proxies/{name}")

    create = _request(
        "POST",
        "/proxies",
        json={"name": name, "listen": listen, "upstream": upstream, "enabled": True},
    )
    if create.status_code not in (200, 201):
        raise ToxiproxyError(f"Failed to create proxy {name}: {create.text}")


def set_proxy_enabled(name: str, enabled: bool) -> None:
    """Drop or restore the proxied path. Toxiproxy has no 'down' toxic."""
    response = _request("POST", f"/proxies/{name}", json={"enabled": enabled})
    if response.status_code not in (200, 201, 204):
        response = _request("PATCH", f"/proxies/{name}", json={"enabled": enabled})
    if response.status_code not in (200, 201, 204):
        raise ToxiproxyError(
            f"Failed to set proxy {name} enabled={enabled}: {response.status_code} {response.text}"
        )


def delete_proxy(name: str) -> None:
    _request("DELETE", f"/proxies/{name}")


def add_down_toxic(proxy_name: str, toxic_name: str = "wifi_drop") -> None:
    """Simulate network drop by blocking upstream traffic."""
    response = _request(
        "POST",
        f"/proxies/{proxy_name}/toxics",
        json={
            "name": toxic_name,
            "type": "down",
            "stream": "upstream",
            "toxicity": 1.0,
        },
    )
    if response.status_code not in (200, 201):
        raise ToxiproxyError(f"Failed to add down toxic: {response.text}")


def remove_toxic(proxy_name: str, toxic_name: str) -> None:
    _request("DELETE", f"/proxies/{proxy_name}/toxics/{toxic_name}")
