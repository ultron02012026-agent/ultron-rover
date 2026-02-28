#!/usr/bin/env python3
"""
Ultron Rover Voice Listener — "Hey Ultron" Architecture

All processing runs locally on the Pi until wake word is detected.
NO audio is stored on disk. Ever. Everything streams through memory.

Flow:
  1. Porcupine wake word engine listens for "Hey Ultron" (on-device, zero API calls)
  2. On detection → beep confirmation → start recording speech
  3. VAD detects end of speech → send audio bytes directly to Mac mini (in memory)
  4. Mac mini transcribes + processes → sends response
  5. Pi plays response on speaker → back to wake word listening

Dependencies:
  - pvporcupine (wake word, on-device)
  - pyaudio (mic input)
  - webrtcvad (speech endpoint detection)
  - requests (send audio to Mac mini)
"""

import pyaudio
import struct
import time
import os
import io
import wave
import json
import subprocess
import threading
import sys

try:
    import pvporcupine
    HAS_PORCUPINE = True
except ImportError:
    HAS_PORCUPINE = False
    print("⚠️  pvporcupine not installed — falling back to energy-based detection")
    print("   Install: pip3 install pvporcupine")

try:
    import webrtcvad
    HAS_VAD = True
except ImportError:
    HAS_VAD = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("⚠️  requests not installed")


# ── Config ────────────────────────────────────────────────────

# Picovoice access key (set via environment variable)
PICOVOICE_ACCESS_KEY = os.environ.get("PICOVOICE_ACCESS_KEY", "")

# Custom wake word model path (train "Hey Ultron" at console.picovoice.ai)
# If not set, falls back to built-in "computer" keyword for testing
WAKE_WORD_PATH = os.environ.get("WAKE_WORD_PATH", "")

# Audio
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16

# Speech recording
MAX_SPEECH_SECONDS = 15
SILENCE_TIMEOUT_MS = 900    # ms of silence to end recording
VAD_MODE = 2                # 0-3, higher = more aggressive filtering
FRAME_DURATION_MS = 30
FRAME_SIZE = int(RATE * FRAME_DURATION_MS / 1000)

# Ultron Mac mini
ULTRON_HOST = os.environ.get("ULTRON_HOST", "ultrons-mini.local")
ULTRON_PORT = int(os.environ.get("ULTRON_PORT", "5555"))
ULTRON_API = f"http://{ULTRON_HOST}:{ULTRON_PORT}"

# Speaker
SPEAKER_DEVICE = os.environ.get("SPEAKER_DEVICE", "plughw:2,0")


class UltronVoice:
    """Hey Ultron wake word + voice command system."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.mic_index = self._find_usb_mic()
        self.running = False
        self.speaking = False
        self._speak_lock = threading.Lock()

        # Wake word engine
        self.porcupine = None
        if HAS_PORCUPINE and PICOVOICE_ACCESS_KEY:
            try:
                if WAKE_WORD_PATH and os.path.exists(WAKE_WORD_PATH):
                    # Custom "Hey Ultron" model
                    self.porcupine = pvporcupine.create(
                        access_key=PICOVOICE_ACCESS_KEY,
                        keyword_paths=[WAKE_WORD_PATH]
                    )
                    print("🎯 Wake word: Hey Ultron (custom model)")
                else:
                    # Fallback to built-in keyword for testing
                    self.porcupine = pvporcupine.create(
                        access_key=PICOVOICE_ACCESS_KEY,
                        keywords=["computer"]
                    )
                    print("🎯 Wake word: 'Computer' (testing mode)")
                    print("   Train 'Hey Ultron' at https://console.picovoice.ai")
            except Exception as e:
                print(f"⚠️  Porcupine init failed: {e}")
                self.porcupine = None

        if not self.porcupine:
            print("🎯 Wake word: energy-based fallback (say anything loud)")

        # VAD for speech endpoint detection
        if HAS_VAD:
            self.vad = webrtcvad.Vad(VAD_MODE)
        else:
            self.vad = None

    def _find_usb_mic(self):
        """Find USB microphone device index."""
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            name = info.get('name', '').lower()
            if 'usb' in name and info.get('maxInputChannels', 0) > 0:
                print(f"🎤 Mic: {info['name']} (index {i})")
                return i
        print("🎤 Mic: default input")
        return None

    def beep(self, freq=800, duration_ms=150):
        """Play a short beep to confirm wake word detected. No disk writes."""
        try:
            subprocess.run(
                ['ffplay', '-nodisp', '-autoexit', '-volume', '80',
                 '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={duration_ms/1000}'],
                capture_output=True, timeout=3,
                env={**os.environ, 'AUDIODEV': SPEAKER_DEVICE}
            )
        except Exception:
            pass

    def speak(self, text):
        """TTS response through speaker. No files saved to disk."""
        if not text or text == '...':
            return
        with self._speak_lock:
            self.speaking = True
            try:
                # Generate TTS to stdout pipe, play directly (no disk)
                espeak = subprocess.Popen(
                    ['espeak', '-v', 'en', '-s', '150', '--stdout', text],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                subprocess.run(
                    ['ffplay', '-nodisp', '-autoexit', '-volume', '100', '-i', 'pipe:0'],
                    stdin=espeak.stdout, capture_output=True, timeout=30,
                    env={**os.environ, 'AUDIODEV': SPEAKER_DEVICE}
                )
                espeak.wait()
            except Exception as e:
                print(f"  TTS error: {e}")
            finally:
                self.speaking = False

    def record_speech(self, stream):
        """
        Record speech after wake word. Returns WAV bytes in memory.
        NOTHING is written to disk.
        """
        frames = []
        silence_frames = 0
        max_frames = int(MAX_SPEECH_SECONDS * 1000 / FRAME_DURATION_MS)
        silence_limit = int(SILENCE_TIMEOUT_MS / FRAME_DURATION_MS)

        print("  🔴 Listening...")

        for _ in range(max_frames):
            try:
                data = stream.read(FRAME_SIZE, exception_on_overflow=False)
            except IOError:
                continue

            frames.append(data)

            # Check for speech end
            is_speech = True
            if self.vad:
                try:
                    is_speech = self.vad.is_speech(data, RATE)
                except Exception:
                    pass

            if not is_speech:
                silence_frames += 1
                if silence_frames >= silence_limit and len(frames) > 10:
                    break
            else:
                silence_frames = 0

        if len(frames) < 5:
            return None

        duration = len(frames) * FRAME_DURATION_MS / 1000
        print(f"  ⏹️  Got {duration:.1f}s")

        # Build WAV in memory — no disk writes
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        return buffer.getvalue()

    def send_to_ultron(self, wav_bytes):
        """Send audio bytes to Mac mini. Nothing touches disk."""
        if not HAS_REQUESTS:
            return None
        try:
            resp = requests.post(
                f"{ULTRON_API}/voice",
                files={'audio': ('speech.wav', wav_bytes, 'audio/wav')},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Can't reach Ultron at {ULTRON_API}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        return None

    def handle_wake(self, stream):
        """Wake word detected — record, send, respond."""
        print("  ✨ Hey Ultron!")

        # Confirmation beep
        self.beep(800, 150)
        time.sleep(0.1)
        self.beep(1200, 100)

        # Record speech (in memory only)
        wav_bytes = self.record_speech(stream)
        if not wav_bytes:
            self.speak("I didn't catch that.")
            return

        # Send to Mac mini
        print("  📤 Processing...")
        response = self.send_to_ultron(wav_bytes)

        # wav_bytes is now garbage collected — never hit disk
        del wav_bytes

        if response:
            text = response.get('text', '')
            if text:
                print(f"  🗣️  {text}")
                self.speak(text)

            commands = response.get('commands', [])
            for cmd in commands:
                print(f"  ⚡ {cmd}")
                # TODO: execute motor/LED/audio commands via Freenove API
        else:
            self.speak("Sorry, I couldn't process that.")

    def run(self):
        """Main loop. Wake word detection runs entirely on-device."""
        print("\n🤖 Ultron Rover Voice System")
        print("=" * 40)

        if self.porcupine:
            frame_length = self.porcupine.frame_length
            sample_rate = self.porcupine.sample_rate
        else:
            frame_length = FRAME_SIZE
            sample_rate = RATE

        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=sample_rate,
            input=True,
            input_device_index=self.mic_index,
            frames_per_buffer=frame_length
        )

        self.running = True
        print(f"👂 Waiting for wake word...\n")

        try:
            while self.running:
                if self.speaking:
                    time.sleep(0.1)
                    continue

                try:
                    pcm = stream.read(frame_length, exception_on_overflow=False)
                except IOError:
                    continue

                if self.porcupine:
                    # Porcupine wake word detection (on-device, zero network)
                    pcm_unpacked = struct.unpack_from(
                        "h" * frame_length, pcm
                    )
                    keyword_index = self.porcupine.process(pcm_unpacked)
                    if keyword_index >= 0:
                        self.handle_wake(stream)
                        print(f"👂 Waiting for wake word...\n")
                else:
                    # Energy-based fallback (for testing without Porcupine)
                    samples = struct.unpack(f'{len(pcm)//2}h', pcm)
                    energy = sum(abs(s) for s in samples) / len(samples)
                    if energy > 2000:  # Loud noise = trigger
                        self.handle_wake(stream)
                        print(f"👂 Waiting for wake word...\n")

        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
        finally:
            stream.stop_stream()
            stream.close()
            if self.porcupine:
                self.porcupine.delete()
            self.audio.terminate()


def main():
    if not PICOVOICE_ACCESS_KEY:
        print("=" * 50)
        print("⚠️  No PICOVOICE_ACCESS_KEY set!")
        print("   Get a free key: https://console.picovoice.ai")
        print("   Then: export PICOVOICE_ACCESS_KEY='your_key'")
        print("   Running in fallback mode (loud noise = trigger)")
        print("=" * 50)

    voice = UltronVoice()
    voice.run()


if __name__ == '__main__':
    main()
