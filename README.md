# Soundbox IoT

Tests for a Paytm Soundbox-style device. A small REST API publishes a payment to MQTT. A device simulator acknowledges it and produces the spoken announcement.

## What you need

- macOS
- Python 3.9 or newer
- Docker Desktop, running
- Port 1883 free

The audio test uses the macOS `say` and `afconvert` commands. On Linux or Windows that test fails. Docker starts the MQTT broker. The first run downloads a speech model and Toxiproxy into `.cache/`.

## Setup

```bash
git clone https://github.com/Mandeep-Singh-Chawla/Soundbox_IoT.git
cd Soundbox_IoT
python3 -m venv .venv
source .venv/bin/activate
pip install pytest-mqtt pytest requests flask vosk
```

## Run the tests

```bash
pytest testing -v
```

You should see 6 passed:

| Test | What it checks |
|---|---|
| `test_soundbox_comes_online` | The device publishes `online` when it connects |
| `test_soundbox_payment_success` | A successful payment is acknowledged and announced |
| `test_soundbox_payment_failure` | The REST API publishes a failed payment, and the device announces it |
| `test_soundbox_multiple_payments` | Several payments are handled in order |
| `test_soundbox_audio_announcement_failure` | The failure announcement is spoken and the transcript matches |
| `test_network_fallback_does_not_drop_announcement` | After a simulated Wi-Fi drop and reconnect, the announcement is still delivered |

## Run the API on its own

```bash
python soundbox_app.py
```

The API listens on port 8081. It expects an MQTT broker on `localhost:1883`.

```bash
curl -X POST http://localhost:8081/payment \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN001","amount":500,"status":"success"}'
```
