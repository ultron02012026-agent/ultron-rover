#!/usr/bin/env python3
"""
Ultron Rover Voice Listener

Listens on the USB microphone for speech, sends it to Ultron (Mac mini)
for processing, and plays back responses on the USB speaker.

Architecture:
  1. VAD (Voice Activity Detection) via webrtcvad - detects when someone's talking
  2. Records speech chunks
  3. Sends audio to Mac mini API for transcription + processing
  4. Receives text response + optional commands (drive, lights, etc.)
  5. Plays TTS response on speaker via espeak/piper

Dependencies (installed by setup):
  - pyaudio (mic input)
  - webrtcvad (voice activity detection)
  - requests (API calls to Mac mini)
"""

import pyaudio
import wave
import struct
import time
import os
import json
import subprocess
import threading
import tempfile
import sys
from pathlib import Path

try:
    import webrtcvad
    HAS_VAD = True
except ImportError:
    HAS_VAD = False
    print("WARNING: webrtcvad not installed, using simple energy-based VAD")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: requests not installed, running in local-only mode")


# ── Audio Config ──────────────────────────────────────────────
RATE = 16000          # 16kHz for speech recognition
CHANNELS = 1          # Mono
FORMAT = pyaudio.paInt16
FRAME_DURATION_MS = 30   # 30ms frames for VAD
FRAME_SIZE = int(RATE * FRAME_DURATION_MS / 1000)  # 480 samples per frame

# VAD sensitivity (0=least aggressive, 3=most aggressive filtering)
VAD_MODE = 2

# Speech detection thresholds
MIN_SPEECH_FRAMES = 10      # Minimum frames to count as speech (~300ms)
MAX_SPEECH_SECONDS = 15     # Max recording length
SILENCE_TIMEOUT_FRAMES = 30 # Frames of silence to end recording (~900ms)
PRE_SPEECH_BUFFER = 10      # Keep N frames before speech detected

# ── Ultron Mac Mini Connection ────────────────────────────────
ULTRON_HOST = os.environ.get("ULTRON_HOST", "ultrons-mini.local")
ULTRON_PORT = int(os.environ.get("ULTRON_PORT", "5555"))
ULTRON_API = f"http://{ULTRON_HOST}:{ULTRON_PORT}"

# ── Audio Output ──────────────────────────────────────────────
SPEAKER_DEVICE = os.environ.get("SPEAKER_DEVICE", "plughw:2,0")


class SimpleVAD:
    """Energy-based VAD fallback when webrtcvad isn't available."""

    def __init__(self, threshold=500):
        self.threshold = threshold

    def is_speech(self, audio_data, sample_rate):
        samples = struct.unpack(f'{len(audio_data)//2}h', audio_data)
        energy = sum(abs(s) for s in samples) / len(samples)
        return energy > self.threshold


class VoiceListener:
    """Continuously listens for speech and processes commands."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.running = False
        self.mic_index = self._find_usb_mic()

        if HAS_VAD:
            self.vad = webrtcvad.Vad(VAD_MODE)
        else:
            self.vad = SimpleVAD()

        # Audio output lock (don't listen while speaking)
        self.speaking = False
        self._speak_lock = threading.Lock()

        print(f"🎤 Mic: device {self.mic_index}")
        print(f"🔊 Speaker: {SPEAKER_DEVICE}")
        print(f"🧠 Ultron API: {ULTRON_API}")

    def _find_usb_mic(self):
        """Find the USB microphone device index."""
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            name = info.get('name', '').lower()
            if 'usb' in name and info.get('maxInputChannels', 0) > 0:
                print(f"  Found USB mic: {info['name']} (index {i})")
                return i
        # Fallback to default input
        print("  No USB mic found, using default input")
        return None

    def _is_speech(self, frame_data):
        """Check if audio frame contains speech."""
        if HAS_VAD:
            try:
                return self.vad.is_speech(frame_data, RATE)
            except Exception:
                return False
        else:
            return self.vad.is_speech(frame_data, RATE)

    def speak(self, text, voice="Whisper"):
        """Play TTS response through the speaker."""
        with self._speak_lock:
            self.speaking = True
            try:
                # Try piper first (better quality), fall back to espeak
                tmp = tempfile.mktemp(suffix='.wav')
                try:
                    # espeak fallback
                    subprocess.run(
                        ['espeak', '-v', 'en', '-s', '140', '-w', tmp, text],
                        capture_output=True, timeout=10
                    )
                except FileNotFoundError:
                    # Last resort: use ffplay with sine wave beep
                    print(f"  No TTS available, printing: {text}")
                    return

                if os.path.exists(tmp):
                    subprocess.run(
                        ['ffplay', '-nodisp', '-autoexit', '-volume', '100',
                         '-af', f'aformat=sample_rates=22050',
                         tmp],
                        capture_output=True, timeout=30,
                        env={**os.environ, 'AUDIODEV': SPEAKER_DEVICE}
                    )
                    os.unlink(tmp)
            finally:
                self.speaking = False

    def record_speech(self, stream):
        """Record audio until speech ends. Returns WAV bytes or None."""
        frames = []
        speech_frames = 0
        silence_frames = 0
        ring_buffer = []  # Pre-speech buffer
        recording = False
        total_frames = 0
        max_frames = int(MAX_SPEECH_SECONDS * 1000 / FRAME_DURATION_MS)

        while total_frames < max_frames:
            try:
                data = stream.read(FRAME_SIZE, exception_on_overflow=False)
            except IOError:
                continue

            total_frames += 1
            is_speech = self._is_speech(data)

            if not recording:
                # Buffer pre-speech audio
                ring_buffer.append(data)
                if len(ring_buffer) > PRE_SPEECH_BUFFER:
                    ring_buffer.pop(0)

                if is_speech:
                    speech_frames += 1
                    if speech_frames >= MIN_SPEECH_FRAMES:
                        # Speech confirmed! Start recording
                        recording = True
                        frames = list(ring_buffer)  # Include pre-speech
                        print("  🔴 Recording...")
                else:
                    speech_frames = max(0, speech_frames - 1)
            else:
                frames.append(data)
                if is_speech:
                    silence_frames = 0
                else:
                    silence_frames += 1
                    if silence_frames >= SILENCE_TIMEOUT_FRAMES:
                        # Speech ended
                        break

        if not recording or len(frames) < MIN_SPEECH_FRAMES:
            return None

        duration = len(frames) * FRAME_DURATION_MS / 1000
        print(f"  ⏹️  Captured {duration:.1f}s of audio")

        # Convert to WAV bytes
        tmp = tempfile.mktemp(suffix='.wav')
        with wave.open(tmp, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        with open(tmp, 'rb') as f:
            wav_bytes = f.read()
        os.unlink(tmp)
        return wav_bytes

    def send_to_ultron(self, wav_bytes):
        """Send recorded audio to Ultron Mac mini for processing."""
        if not HAS_REQUESTS:
            print("  No requests library — can't reach Ultron")
            return None

        try:
            resp = requests.post(
                f"{ULTRON_API}/voice",
                files={'audio': ('speech.wav', wav_bytes, 'audio/wav')},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"  Ultron API error: {resp.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            print(f"  Can't reach Ultron at {ULTRON_API}")
            return None
        except Exception as e:
            print(f"  Error sending to Ultron: {e}")
            return None

    def process_response(self, response):
        """Process Ultron's response — speak and/or execute commands."""
        if not response:
            return

        # Speak the response
        text = response.get('text', '')
        if text:
            print(f"  🗣️  Ultron says: {text}")
            self.speak(text)

        # Execute motor commands if any
        commands = response.get('commands', [])
        for cmd in commands:
            print(f"  ⚡ Command: {cmd}")
            # Commands will be handled by rover_api integration

    def listen_loop(self):
        """Main listening loop."""
        print("\n🤖 Ultron Rover Voice System")
        print("=" * 40)
        print("Listening for speech...\n")

        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=self.mic_index,
            frames_per_buffer=FRAME_SIZE
        )

        self.running = True
        idle_count = 0

        try:
            while self.running:
                # Don't listen while speaking
                if self.speaking:
                    time.sleep(0.1)
                    continue

                # Check for speech
                try:
                    data = stream.read(FRAME_SIZE, exception_on_overflow=False)
                except IOError:
                    continue

                if self._is_speech(data):
                    # Potential speech detected — try to record full utterance
                    wav_bytes = self.record_speech(stream)

                    if wav_bytes:
                        print("  📤 Sending to Ultron...")
                        response = self.send_to_ultron(wav_bytes)
                        self.process_response(response)
                        print("  👂 Listening...\n")
                else:
                    idle_count += 1
                    if idle_count % 1000 == 0:
                        # Heartbeat every ~30s
                        sys.stdout.write('.')
                        sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n\n🛑 Stopping voice listener...")
        finally:
            stream.stop_stream()
            stream.close()
            self.running = False

    def shutdown(self):
        """Clean shutdown."""
        self.running = False
        self.audio.terminate()


def main():
    listener = VoiceListener()
    try:
        listener.listen_loop()
    finally:
        listener.shutdown()


if __name__ == '__main__':
    main()
