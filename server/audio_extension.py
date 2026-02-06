#!/usr/bin/env python3
"""
Audio Extension for Freenove Server

Adds CMD_AUDIO command to play sound files through USB speaker.
Copy this to the Pi's Freenove Code/Server folder and import it in main.py.

Usage:
    from audio_extension import AudioPlayer
    audio = AudioPlayer()
    audio.play("ow_1.mp3")  # plays ~/audio/ow_1.mp3
"""

import os
import subprocess
import threading
import random
from pathlib import Path


class AudioPlayer:
    """Play audio files through the USB speaker."""
    
    def __init__(self, audio_dir: str = "~/audio"):
        self.audio_dir = Path(audio_dir).expanduser()
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._playing = False
        self._lock = threading.Lock()
        
        # Find audio player
        self._player = self._find_player()
        if not self._player:
            print("⚠️ No audio player found. Install mpv, ffplay, or aplay.")
    
    def _find_player(self) -> str:
        """Find an available audio player."""
        players = ["mpv", "ffplay", "aplay", "paplay"]
        for player in players:
            try:
                subprocess.run(
                    ["which", player], 
                    capture_output=True, 
                    check=True
                )
                return player
            except subprocess.CalledProcessError:
                continue
        return ""
    
    def play(self, filename: str, blocking: bool = False):
        """
        Play an audio file.
        
        Args:
            filename: Name of file in audio_dir (e.g., "ow_1.mp3")
            blocking: If True, wait for playback to finish
        """
        if not self._player:
            print(f"Cannot play {filename}: no audio player available")
            return
        
        filepath = self.audio_dir / filename
        if not filepath.exists():
            print(f"Audio file not found: {filepath}")
            return
        
        if blocking:
            self._play_sync(str(filepath))
        else:
            threading.Thread(
                target=self._play_sync, 
                args=(str(filepath),),
                daemon=True
            ).start()
    
    def _play_sync(self, filepath: str):
        """Play audio synchronously."""
        with self._lock:
            if self._playing:
                return  # Don't overlap audio
            self._playing = True
        
        try:
            if self._player == "mpv":
                cmd = ["mpv", "--no-video", "--really-quiet", filepath]
            elif self._player == "ffplay":
                cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", filepath]
            elif self._player == "aplay":
                # aplay only handles WAV, need to convert or use different approach
                cmd = ["aplay", "-q", filepath]
            elif self._player == "paplay":
                cmd = ["paplay", filepath]
            else:
                cmd = [self._player, filepath]
            
            subprocess.run(cmd, capture_output=True)
            
        except Exception as e:
            print(f"Error playing audio: {e}")
        finally:
            with self._lock:
                self._playing = False
    
    def play_random(self, prefix: str = "ow"):
        """Play a random audio file matching the prefix."""
        matching = list(self.audio_dir.glob(f"{prefix}*"))
        if matching:
            self.play(random.choice(matching).name)
        else:
            print(f"No audio files matching '{prefix}*' in {self.audio_dir}")
    
    def list_files(self) -> list:
        """List available audio files."""
        return [f.name for f in self.audio_dir.iterdir() if f.is_file()]
    
    def stop(self):
        """Stop current playback (kills all instances of the player)."""
        if self._player:
            subprocess.run(["pkill", "-9", self._player], capture_output=True)


class CollisionAudio:
    """
    Collision-triggered audio player.
    
    Monitors distance and plays audio when collision detected.
    """
    
    # Audio categories for different collision types
    CLIPS = {
        "impact": ["ow_1.wav", "ow_2.wav", "ow_3.wav", "dammit.wav", "wilhelm.wav"],
        "close_call": ["whoa.wav"],
        "stuck": ["stuck.wav", "meant_to_do_that.wav", "why.wav"],
        "dramatic": ["wilhelm.wav", "nooo.wav"],
    }
    
    def __init__(self, audio_player: AudioPlayer):
        self.audio = audio_player
        self._last_distance = float('inf')
        self._stuck_count = 0
        
    def on_distance_update(self, distance: float) -> bool:
        """
        Called with new distance reading. Returns True if collision detected.
        
        Args:
            distance: Distance in cm from ultrasonic sensor
            
        Returns:
            True if collision event triggered
        """
        collision = False
        
        # Sudden impact: distance dropped significantly
        if self._last_distance - distance > 20:
            self._play_random("impact")
            collision = True
            self._stuck_count = 0
            
        # Close call: got very close
        elif distance < 10 and self._last_distance >= 10:
            self._play_random("close_call")
            collision = True
            
        # Stuck: distance unchanged and very close for multiple readings
        elif distance < 15 and abs(distance - self._last_distance) < 2:
            self._stuck_count += 1
            if self._stuck_count >= 5:
                self._play_random("stuck")
                self._stuck_count = 0
                collision = True
        else:
            self._stuck_count = 0
        
        self._last_distance = distance
        return collision
    
    def _play_random(self, category: str):
        """Play random clip from category."""
        clips = self.CLIPS.get(category, [])
        available = [c for c in clips if (self.audio.audio_dir / c).exists()]
        if available:
            self.audio.play(random.choice(available))
        elif clips:
            # Fall back to any available audio
            all_files = self.audio.list_files()
            if all_files:
                self.audio.play(random.choice(all_files))


# ========== INTEGRATION WITH FREENOVE SERVER ==========

def patch_freenove_server():
    """
    Monkey-patch the Freenove server to add audio support.
    
    Call this at the start of main.py after imports:
    
        from audio_extension import patch_freenove_server, audio_player
        patch_freenove_server()
    
    Then CMD_AUDIO#filename commands will work.
    """
    # This would be imported and called from their main.py
    # The actual integration depends on how they structure the command handling
    pass


# Global instances for easy import
audio_player = AudioPlayer()
collision_audio = CollisionAudio(audio_player)


if __name__ == "__main__":
    # Test audio playback
    print("Audio Extension Test")
    print(f"Audio directory: {audio_player.audio_dir}")
    print(f"Player: {audio_player._player}")
    print(f"Available files: {audio_player.list_files()}")
    
    # Create test audio file using espeak if available
    test_file = audio_player.audio_dir / "test.wav"
    if not test_file.exists():
        try:
            subprocess.run([
                "espeak", "-w", str(test_file), "Hello, I am Ultron"
            ], check=True)
            print(f"Created test audio: {test_file}")
        except:
            print("Could not create test audio (espeak not available)")
    
    if test_file.exists():
        print("Playing test audio...")
        audio_player.play("test.wav", blocking=True)
        print("Done!")
