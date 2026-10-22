"""
Network fallback test: WiFi -> 4G must not drop payment announcement.

Scenario (positive):
- Soundbox device connects to broker through Toxiproxy.
- Payment command is published while the path is up.
- Toxiproxy disables the proxy (simulated WiFi loss).
- Proxy is enabled again (simulated 4G fallback).
- Device reconnects, payment is retried, announcement is still delivered.

Toxiproxy is started automatically when it is not already running.
"""
from __future__ import annotations

import json
import platform
import stat
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from pytest_mqtt.util import delay
from testing.soundbox_simulator import (
    TOPIC_PAYMENT_ACK,
    TOPIC_PAYMENT_ANNOUNCE,
    TOPIC_PAYMENT_COMMAND,
    SoundboxSimulator,
)
from testing.toxiproxy_helper import (
    delete_proxy,
    ensure_proxy,
    is_toxiproxy_running,
    set_proxy_enabled,
)

PROXY_NAME = "mqtt_soundbox"
PROXY_LISTEN = "127.0.0.1:1884"
TOXIPROXY_VERSION = "2.12.0"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"


def _toxiproxy_binary() -> Path:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    system = platform.system().lower()
    if system == "darwin":
        os_name = "darwin"
    elif system == "linux":
        os_name = "linux"
    else:
        raise RuntimeError(f"Unsupported OS for Toxiproxy auto-start: {system}")
    filename = f"toxiproxy-server-{os_name}-{arch}"
    binary = CACHE_DIR / filename
    if binary.exists():
        return binary
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://github.com/Shopify/toxiproxy/releases/download/"
        f"v{TOXIPROXY_VERSION}/{filename}"
    )
    urllib.request.urlretrieve(url, binary)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return binary


@pytest.fixture(scope="session")
def toxiproxy_server():
    if is_toxiproxy_running():
        yield
        return

    binary = _toxiproxy_binary()
    process = subprocess.Popen(
        [str(binary)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if is_toxiproxy_running():
            break
        if process.poll() is not None:
            raise RuntimeError(f"toxiproxy-server exited early ({process.returncode})")
        time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Toxiproxy did not become ready on localhost:8474")

    yield
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="module")
def mqtt_proxy(mosquitto, toxiproxy_server):
    host, port = mosquitto
    ensure_proxy(PROXY_NAME, listen=PROXY_LISTEN, upstream=f"{host}:{port}")
    yield PROXY_LISTEN
    delete_proxy(PROXY_NAME)


def _start_simulator_on_proxy(proxy_listen: str, client_id: str) -> SoundboxSimulator:
    proxy_host, proxy_port = proxy_listen.split(":")
    simulator = SoundboxSimulator(host=proxy_host, port=int(proxy_port), client_id=client_id)
    simulator.start()
    simulator.wait_until_ready()
    return simulator


@pytest.fixture
def soundbox_via_proxy(mqtt_proxy, capmqtt):
    """
    Device connects through Toxiproxy (simulates WiFi path).
    capmqtt stays on the direct broker path as the test observer.
    """
    simulator = _start_simulator_on_proxy(mqtt_proxy, client_id="soundbox-via-proxy")
    yield simulator
    simulator.stop()


@pytest.mark.capmqtt_decode_utf8
def test_network_fallback_does_not_drop_announcement(mosquitto, mqtt_proxy, soundbox_via_proxy, capmqtt):
    """
    Drop the network mid-transaction; after restore, reconnect, and retry,
    the payment announcement must still be delivered.
    """
    payment = {
        "transaction_id": "TXN_NET_001",
        "amount": 500,
        "status": "success",
    }

    capmqtt.publish(topic=TOPIC_PAYMENT_COMMAND, payload=json.dumps(payment))
    delay(0.2)

    set_proxy_enabled(PROXY_NAME, enabled=False)
    delay(0.3)
    set_proxy_enabled(PROXY_NAME, enabled=True)
    delay(0.2)

    soundbox_via_proxy.stop()
    delay(0.2)
    reconnected = _start_simulator_on_proxy(mqtt_proxy, client_id="soundbox-via-proxy-retry")

    capmqtt.publish(topic=TOPIC_PAYMENT_COMMAND, payload=json.dumps(payment))
    delay(0.5)

    try:
        ack_messages = [
            json.loads(msg.payload)
            for msg in capmqtt.messages
            if msg.topic == TOPIC_PAYMENT_ACK
            and json.loads(msg.payload).get("transaction_id") == "TXN_NET_001"
        ]
        announce_messages = [
            json.loads(msg.payload)
            for msg in capmqtt.messages
            if msg.topic == TOPIC_PAYMENT_ANNOUNCE
            and json.loads(msg.payload).get("transaction_id") == "TXN_NET_001"
        ]

        assert len(ack_messages) >= 1, "Ack was not delivered after network fallback"
        assert len(announce_messages) >= 1, "Announcement was dropped during network fallback"
        assert announce_messages[-1]["announcement"] == "Payment received of Rupees 500"
    finally:
        reconnected.stop()
