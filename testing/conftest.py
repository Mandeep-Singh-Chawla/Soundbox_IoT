"""Fixtures shared by Soundbox tests."""
from __future__ import annotations

import os
import threading
import time

import pytest
import requests
from werkzeug.serving import make_server

from testing.soundbox_simulator import SoundboxSimulator


@pytest.fixture
def soundbox(mosquitto, capmqtt):
    """
    capmqtt is listed first so it subscribes to the broker before
    the Soundbox connects and publishes its online status message.
    """
    host, port = mosquitto
    simulator = SoundboxSimulator(host=host, port=port)
    simulator.start()
    simulator.wait_until_ready()
    yield simulator
    simulator.stop()


@pytest.fixture
def soundbox_api(mosquitto):
    """Start the payment REST API against the test MQTT broker."""
    host, port = mosquitto
    previous_host = os.environ.get("MQTT_HOST")
    previous_port = os.environ.get("MQTT_PORT")
    os.environ["MQTT_HOST"] = str(host)
    os.environ["MQTT_PORT"] = str(port)

    from soundbox_app import app

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_host, api_port = server.server_address
    base_url = f"http://{api_host}:{api_port}"

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.2)
            if response.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)
    else:
        server.shutdown()
        raise RuntimeError("Soundbox API did not become ready")

    yield base_url

    server.shutdown()
    thread.join(timeout=2)
    if previous_host is None:
        os.environ.pop("MQTT_HOST", None)
    else:
        os.environ["MQTT_HOST"] = previous_host
    if previous_port is None:
        os.environ.pop("MQTT_PORT", None)
    else:
        os.environ["MQTT_PORT"] = previous_port
