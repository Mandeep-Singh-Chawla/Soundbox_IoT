"""
Paytm Soundbox backend service (simulating dev's code).

REST API that receives payment requests and publishes them
to the MQTT broker so the Soundbox device can announce them.

Usage:
    python soundbox_app.py

API:
    POST http://localhost:8081/payment
    Body: {"transaction_id": "TXN001", "amount": 500, "status": "success"}
"""
import json
import os

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request

TOPIC_PAYMENT_COMMAND = "soundbox/payment/command"

app = Flask(__name__)


def mqtt_endpoint():
    """Read broker settings at call time so tests can point at the fixture broker."""
    host = os.environ.get("MQTT_HOST", "localhost")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    return host, port


def get_mqtt_client():
    """Create and connect a Paho MQTT client."""
    host, port = mqtt_endpoint()
    if not hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(client_id="soundbox-app")
    else:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="soundbox-app")
    client.connect(host, port)
    return client


@app.route("/payment", methods=["POST"])
def process_payment():
    """
    Receive a payment request and publish it to the MQTT broker.

    Request body:
        {
            "transaction_id": "TXN001",
            "amount": 500,
            "status": "success"   # or "failed"
        }

    Response:
        {"message": "Payment published", "transaction_id": "TXN001"}
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    transaction_id = data.get("transaction_id")
    amount = data.get("amount")
    status = data.get("status")

    if not all([transaction_id, amount, status]):
        return jsonify({"error": "transaction_id, amount and status are required"}), 400

    if status not in ("success", "failed"):
        return jsonify({"error": "status must be 'success' or 'failed'"}), 400

    # Publish payment command to MQTT broker
    # Soundbox device (simulator or real hardware) will pick this up
    payload = json.dumps({
        "transaction_id": transaction_id,
        "amount": amount,
        "status": status,
    })

    client = get_mqtt_client()
    message_info = client.publish(TOPIC_PAYMENT_COMMAND, payload)
    message_info.wait_for_publish(timeout=2)
    client.disconnect()

    return jsonify({
        "message": "Payment published to Soundbox",
        "transaction_id": transaction_id,
        "amount": amount,
        "status": status,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    api_port = int(os.environ.get("PORT", "8081"))
    mqtt_host, mqtt_port = mqtt_endpoint()
    print("Starting Soundbox backend service...")
    print(f"MQTT broker: {mqtt_host}:{mqtt_port}")
    print(f"REST API: http://localhost:{api_port}")
    app.run(host="0.0.0.0", port=api_port, debug=False)
