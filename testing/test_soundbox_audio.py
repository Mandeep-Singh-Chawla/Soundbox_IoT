"""
Audio verification for Soundbox failure announcements.

The simulator turns the announcement it would speak into a 16 kHz WAV.
This test transcribes that file and checks the spoken phrase.

Vosk model (downloaded on first run):
    .cache/vosk-model-small-en-us-0.15
"""
from __future__ import annotations

import json
import wave
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import pytest
import requests

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = Path(__file__).resolve().parents[1] / ".cache" / "vosk-model-small-en-us-0.15"

_model = None


def _ensure_vosk_model() -> Path:
    if (MODEL_DIR / "conf" / "model.conf").exists():
        return MODEL_DIR
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive = MODEL_DIR.parent / "vosk-model-small-en-us-0.15.zip"
    if not archive.exists():
        urlretrieve(MODEL_URL, archive)
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(MODEL_DIR.parent)
    if not (MODEL_DIR / "conf" / "model.conf").exists():
        raise RuntimeError(f"Vosk model missing after extract: {MODEL_DIR}")
    return MODEL_DIR


def _normalize_text(value: str) -> str:
    text = " ".join(value.lower().strip().split())
    return (
        text.replace("one thousand", "1000")
        .replace("a thousand", "1000")
        .replace("1,000", "1000")
        .replace(",", "")
    )


def _transcribe(wav_path: str) -> str:
    vosk = pytest.importorskip("vosk")
    global _model
    if _model is None:
        vosk.SetLogLevel(-1)
        _model = vosk.Model(str(_ensure_vosk_model()))

    with wave.open(wav_path, "rb") as audio:
        if audio.getnchannels() != 1 or audio.getframerate() != 16000:
            raise AssertionError(
                f"Expected 16 kHz mono WAV, got {audio.getframerate()} Hz "
                f"{audio.getnchannels()} ch"
            )
        recognizer = vosk.KaldiRecognizer(_model, audio.getframerate())
        while True:
            frames = audio.readframes(4000)
            if not frames:
                break
            recognizer.AcceptWaveform(frames)
        result = json.loads(recognizer.FinalResult())
    return result.get("text", "")


@pytest.mark.capmqtt_decode_utf8
def test_soundbox_audio_announcement_failure(soundbox, soundbox_api, capmqtt, tmp_path):
    """
    Failure payment is spoken by the simulator and the transcript matches.
    """
    wav_path = tmp_path / "announcement.wav"
    soundbox.announcement_wav_path = str(wav_path)
    soundbox.speech_ready.clear()

    payment = {
        "transaction_id": "TXN_AUDIO_001",
        "amount": 1000,
        "status": "failed",
    }
    response = requests.post(f"{soundbox_api}/payment", json=payment, timeout=5)
    assert response.status_code == 200, response.text
    assert soundbox.speech_ready.wait(timeout=20), "Announcement speech was not written"

    transcript = _normalize_text(_transcribe(str(wav_path)))
    expected_snippet = _normalize_text("payment failed for rupees 1000")
    assert expected_snippet in transcript, (
        f"Expected spoken snippet '{expected_snippet}' not found. "
        f"Transcript: '{transcript}'"
    )
