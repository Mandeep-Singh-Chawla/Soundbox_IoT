"""
Paytm Soundbox integration tests.

These tests simulate a Paytm Soundbox device connected to an MQTT broker.
The Soundbox:
  - Subscribes to payment commands on  : soundbox/payment/command
  - Publishes payment acknowledgement  : soundbox/payment/ack
  - Publishes spoken announcement      : soundbox/payment/announce
  - Publishes device online status     : soundbox/device/status
"""
import json

import pytest
import requests

from testing.soundbox_simulator import (
    TOPIC_DEVICE_STATUS,
    TOPIC_PAYMENT_ACK,
    TOPIC_PAYMENT_ANNOUNCE,
    TOPIC_PAYMENT_COMMAND,
)


@pytest.mark.capmqtt_decode_utf8
def test_soundbox_comes_online(mosquitto, soundbox, capmqtt):
    """
    When Soundbox connects to the broker, it publishes an online status message.
    """
    from pytest_mqtt.util import delay
    delay(0.3)

    status_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_DEVICE_STATUS
    ]

    assert len(status_messages) >= 1
    assert status_messages[0]["device_id"] == "SB-001"
    assert status_messages[0]["status"] == "online"


@pytest.mark.capmqtt_decode_utf8
def test_soundbox_payment_success(mosquitto, soundbox, capmqtt):
    """
    When a successful payment command is published, the Soundbox:
    - acknowledges the transaction
    - announces the payment amount aloud
    """
    from pytest_mqtt.util import delay

    payment = {
        "transaction_id": "TXN001",
        "amount": 500,
        "status": "success",
    }
    capmqtt.publish(topic=TOPIC_PAYMENT_COMMAND, payload=json.dumps(payment))
    delay(0.3)

    # Verify acknowledgement
    ack_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ACK
    ]
    assert len(ack_messages) >= 1
    assert ack_messages[0]["transaction_id"] == "TXN001"
    assert ack_messages[0]["ack"] == "received"

    # Verify announcement
    announce_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ANNOUNCE
    ]
    assert len(announce_messages) >= 1
    assert announce_messages[0]["announcement"] == "Payment received of Rupees 500"


@pytest.mark.capmqtt_decode_utf8
def test_soundbox_payment_failure(mosquitto, soundbox, soundbox_api, capmqtt):
    """
    When a failed payment command is published, the Soundbox:
    - acknowledges the transaction
    - announces the payment failure

    Triggers the REST API, which publishes to the MQTT broker.
    """
    from pytest_mqtt.util import delay

    payment = {
        "transaction_id": "TXN002",
        "amount": 1000,
        "status": "failed",
    }

    response = requests.post(f"{soundbox_api}/payment", json=payment, timeout=5)
    assert response.status_code == 200, response.text

    delay(0.3)

    # Verify acknowledgement
    ack_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ACK
    ]
    assert len(ack_messages) >= 1
    assert ack_messages[0]["transaction_id"] == "TXN002"

    # Verify failure announcement
    announce_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ANNOUNCE
    ]
    assert len(announce_messages) >= 1
    assert announce_messages[0]["announcement"] == "Payment failed for Rupees 1000"


@pytest.mark.capmqtt_decode_utf8
def test_soundbox_multiple_payments(mosquitto, soundbox, capmqtt):
    """
    Soundbox handles multiple payment commands in sequence correctly.
    """
    from pytest_mqtt.util import delay

    payments = [
        {"transaction_id": "TXN010", "amount": 200, "status": "success"},
        {"transaction_id": "TXN011", "amount": 750, "status": "success"},
        {"transaction_id": "TXN012", "amount": 300, "status": "failed"},
    ]

    for payment in payments:
        capmqtt.publish(topic=TOPIC_PAYMENT_COMMAND, payload=json.dumps(payment))
        delay(0.2)

    ack_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ACK
    ]
    announce_messages = [
        json.loads(msg.payload)
        for msg in capmqtt.messages
        if msg.topic == TOPIC_PAYMENT_ANNOUNCE
    ]

    assert len(ack_messages) == 3
    assert [m["transaction_id"] for m in ack_messages] == ["TXN010", "TXN011", "TXN012"]

    assert announce_messages[0]["announcement"] == "Payment received of Rupees 200"
    assert announce_messages[1]["announcement"] == "Payment received of Rupees 750"
    assert announce_messages[2]["announcement"] == "Payment failed for Rupees 300"
