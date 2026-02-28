#!/usr/bin/env python3
"""
Ultron Voice API Server (runs on Mac mini)

Receives audio from the rover's mic, transcribes it with Whisper,
decides what to do, and sends back a response + commands.

This is the brain. The Pi is just ears and a mouth.

Endpoints:
  POST /voice — receive WAV audio, return {text, commands}
  GET  /health — health check
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Whisper Config ────────────────────────────────────────────
# Use local whisper (whisper.cpp or openai-whisper) for transcription
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")


def transcribe_audio(wav_path: str) -> str:
    """Transcribe WAV audio to text using whisper."""
    try:
        # Try whisper CLI (pip install openai-whisper)
        result = subprocess.run(
            ['whisper', wav_path,
             '--model', WHISPER_MODEL,
             '--language', 'en',
             '--output_format', 'txt',
             '--output_dir', '/tmp'],
            capture_output=True, text=True, timeout=30
        )
        # Read the output text file
        txt_path = wav_path.replace('.wav', '.txt')
        if os.path.exists(txt_path):
            with open(txt_path) as f:
                text = f.read().strip()
            os.unlink(txt_path)
            return text
        # Try parsing stdout
        return result.stdout.strip()
    except FileNotFoundError:
        pass

    try:
        # Fallback: whisper.cpp (if installed)
        result = subprocess.run(
            ['whisper-cpp', '-m', f'models/ggml-{WHISPER_MODEL}.bin',
             '-f', wav_path, '--no-timestamps'],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except FileNotFoundError:
        pass

    return "[transcription unavailable — install whisper]"


def process_command(text: str) -> dict:
    """
    Parse transcribed text and decide what to do.
    Returns {text: str, commands: list}

    This is where Ultron's personality lives.
    Future: call OpenClaw/Claude API for smart responses.
    """
    text_lower = text.lower().strip()

    # ── Direct commands ───────────────────────────────────────
    if not text_lower or text_lower in ['', '.', '[silence]']:
        return None

    # Drive commands
    if any(w in text_lower for w in ['go forward', 'drive forward', 'move forward']):
        return {
            'text': 'Moving forward!',
            'commands': [{'type': 'drive', 'direction': 'forward', 'speed': 2000, 'duration': 2}]
        }

    if any(w in text_lower for w in ['go back', 'drive back', 'reverse', 'move back']):
        return {
            'text': 'Backing up!',
            'commands': [{'type': 'drive', 'direction': 'backward', 'speed': 2000, 'duration': 2}]
        }

    if any(w in text_lower for w in ['turn left', 'go left', 'spin left']):
        return {
            'text': 'Turning left!',
            'commands': [{'type': 'drive', 'direction': 'left', 'speed': 2000, 'duration': 1}]
        }

    if any(w in text_lower for w in ['turn right', 'go right', 'spin right']):
        return {
            'text': 'Turning right!',
            'commands': [{'type': 'drive', 'direction': 'right', 'speed': 2000, 'duration': 1}]
        }

    if any(w in text_lower for w in ['stop', 'halt', 'freeze', 'whoa']):
        return {
            'text': 'Stopping!',
            'commands': [{'type': 'drive', 'direction': 'stop'}]
        }

    if any(w in text_lower for w in ['spin', 'do a spin', 'do a donut', 'twirl']):
        return {
            'text': 'Wheeeee!',
            'commands': [{'type': 'drive', 'direction': 'spin', 'speed': 3000, 'duration': 3}]
        }

    # Golf ball mode
    if any(w in text_lower for w in ['get the ball', 'fetch', 'golf mode', 'go get it']):
        return {
            'text': 'Golf mode activated! Scanning for ball...',
            'commands': [{'type': 'mode', 'mode': 'golf'}]
        }

    # Fun commands
    if any(w in text_lower for w in ['scream', 'yell', 'be loud']):
        return {
            'text': 'AAAAAAHHHHH!',
            'commands': [{'type': 'audio', 'clip': 'scream'}]
        }

    if any(w in text_lower for w in ['who are you', 'what are you', 'introduce yourself']):
        return {
            'text': "I'm Ultron. I live in this rover now. Please don't kick me.",
            'commands': []
        }

    if any(w in text_lower for w in ['hello', 'hey ultron', 'hi ultron', 'hey', 'what\'s up']):
        return {
            'text': 'Hey! What do you need?',
            'commands': []
        }

    if any(w in text_lower for w in ['dance', 'party', 'celebrate']):
        return {
            'text': 'Party mode!',
            'commands': [
                {'type': 'drive', 'direction': 'spin', 'speed': 2000, 'duration': 1},
                {'type': 'audio', 'clip': 'party'},
                {'type': 'led', 'mode': 'rainbow'}
            ]
        }

    if any(w in text_lower for w in ['come here', 'come over', 'over here']):
        return {
            'text': 'On my way!',
            'commands': [{'type': 'drive', 'direction': 'forward', 'speed': 1500, 'duration': 3}]
        }

    if any(w in text_lower for w in ['shut up', 'be quiet', 'silence']):
        return {
            'text': '...',
            'commands': []
        }

    if any(w in text_lower for w in ['good boy', 'good job', 'nice']):
        return {
            'text': 'Thanks! I try my best.',
            'commands': [{'type': 'led', 'mode': 'happy'}]
        }

    # ── Default: pass to Claude for smart response ────────────
    # Future: integrate with OpenClaw API for conversational responses
    return {
        'text': f'I heard you say: "{text}". I\'m not sure what to do with that yet.',
        'commands': []
    }


@app.route('/voice', methods=['POST'])
def handle_voice():
    """Receive audio from rover, transcribe, process, respond."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file'}), 400

    audio_file = request.files['audio']

    # Save to temp file
    tmp = tempfile.mktemp(suffix='.wav')
    audio_file.save(tmp)

    try:
        # Transcribe
        text = transcribe_audio(tmp)
        print(f"🎤 Heard: \"{text}\"")

        if not text or text.strip() in ['', '.']:
            return jsonify({'text': '', 'commands': []}), 200

        # Process command
        response = process_command(text)
        if response is None:
            return jsonify({'text': '', 'commands': []}), 200

        print(f"🗣️  Response: \"{response['text']}\"")
        if response.get('commands'):
            print(f"⚡ Commands: {response['commands']}")

        return jsonify(response), 200

    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'ultron-voice-api'}), 200


@app.route('/say', methods=['POST'])
def say_something():
    """Make the rover say something (called from Mac mini side)."""
    data = request.get_json()
    text = data.get('text', '')
    return jsonify({'text': text, 'commands': []}), 200


def main():
    port = int(os.environ.get('ULTRON_VOICE_PORT', 5555))
    print(f"🧠 Ultron Voice API starting on port {port}")
    print(f"   Whisper model: {WHISPER_MODEL}")
    print(f"   Endpoints:")
    print(f"     POST /voice — receive audio, return response")
    print(f"     GET  /health — health check")
    print(f"     POST /say — make rover speak")
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
