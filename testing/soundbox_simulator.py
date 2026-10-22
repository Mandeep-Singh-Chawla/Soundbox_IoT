"""
Paytm Soundbox device simulator.

Simulates the behavior of a Paytm Soundbox device that:
- Subscribes to payment command topics
- Publishes payment acknowledgement and announcement events
"""
import json
import subprocess
import threading

import paho.mqtt.client as mqtt

from pytest_mqtt.util import delay

TOPIC_PAYMENT_COMMAND = "soundbox/payment/command"
TOPIC_PAYMENT_ACK = "soundbox/payment/ack"
TOPIC_PAYMENT_ANNOUNCE = "soundbox/payment/announce"
TOPIC_DEVICE_STATUS = "soundbox/device/status"


class SoundboxSimulator(threading.Thread):
    """
    Simulates a Paytm Soundbox device connected to an MQTT broker.

    On receiving a payment command, it:
    1. Publishes an acknowledgement back.
    2. Publishes an announcement (what the Soundbox would speak aloud).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        client_id: str = "soundbox-simulator",
    ) -> None:
        super().__init__(daemon=True)
        self.host = host
        self.port = int(port)
        self.announcement_wav_path = None
        self.speech_ready = threading.Event()
        self._ready = threading.Event()

        if not hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(client_id=client_id)
        else:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(self.host, self.port)

    def _on_connect(self, client, userdata, flags, *args) -> None:
        self.client.subscribe(TOPIC_PAYMENT_COMMAND)
        self._ready.set()
        # Publish status in a separate thread so the paho network loop
        # is not blocked and can still receive/respond to payment commands.
        threading.Thread(target=self._publish_online_status, daemon=True).start()

    def _publish_online_status(self) -> None:
        # Small delay so capmqtt has time to subscribe before status arrives.
        delay(0.15)
        self.client.publish(
            TOPIC_DEVICE_STATUS,
            json.dumps({"device_id": "SB-001", "status": "online"}),
        )

    def _on_message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        transaction_id = data.get("transaction_id", "UNKNOWN")
        amount = data.get("amount", 0)
        status = data.get("status", "unknown")

        # Publish acknowledgement
        self.client.publish(
            TOPIC_PAYMENT_ACK,
            json.dumps({
                "transaction_id": transaction_id,
                "ack": "received",
            }),
        )

        # Publish what Soundbox would announce aloud
        if status == "success":
            announcement = f"Payment received of Rupees {amount}"
        else:
            announcement = f"Payment failed for Rupees {amount}"

        self.client.publish(
            TOPIC_PAYMENT_ANNOUNCE,
            json.dumps({
                "transaction_id": transaction_id,
                "announcement": announcement,
            }),
        )
        if self.announcement_wav_path:
            write_speech_wav(announcement, self.announcement_wav_path)
            self.speech_ready.set()

    def run(self) -> None:
        self.client.loop_start()
        self._ready.wait(timeout=5)

    def wait_until_ready(self, timeout: float = 5.0) -> None:
        self._ready.wait(timeout=timeout)

    def stop(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass
        self.client.loop_stop()


def write_speech_wav(text: str, wav_path: str) -> None:
    """Synthesize announcement speech to a 16 kHz WAV (macOS say + afconvert)."""
    aiff_path = wav_path + ".aiff"
    spoken = subprocess.run(
        ["say", "-v", "Samantha", "-r", "150", "-o", aiff_path, text],
        capture_output=True,
        timeout=30,
    )
    if spoken.returncode != 0:
        subprocess.run(["say", "-o", aiff_path, text], check=True, timeout=30)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", aiff_path, wav_path],
        check=True,
        timeout=30,
    )
