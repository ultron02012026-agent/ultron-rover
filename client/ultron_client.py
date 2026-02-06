#!/usr/bin/env python3
"""
Ultron Rover Client - runs on Mac mini to control the rover
"""

import socket
import struct
import threading
import time
import numpy as np
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum
import io

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class RoverState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SensorData:
    distance: float = 0.0  # ultrasonic distance in cm
    light_left: float = 0.0
    light_right: float = 0.0
    ir_left: float = 0.0
    ir_center: float = 0.0
    ir_right: float = 0.0
    battery: float = 0.0


class UltronRover:
    """Client for controlling the Freenove 4WD car from the Mac mini."""
    
    CMD_PORT = 5000
    VIDEO_PORT = 8000
    
    def __init__(self, host: str = "raspberrypi.local"):
        self.host = host
        self.state = RoverState.DISCONNECTED
        
        # Sockets
        self._cmd_socket: Optional[socket.socket] = None
        self._video_socket: Optional[socket.socket] = None
        
        # Threading
        self._cmd_thread: Optional[threading.Thread] = None
        self._video_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Sensor data
        self.sensors = SensorData()
        self._sensor_lock = threading.Lock()
        
        # Video
        self._latest_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        
        # Callbacks
        self._on_frame: Optional[Callable[[bytes], None]] = None
        self._on_collision: Optional[Callable[[float], None]] = None
        self._on_sensor_update: Optional[Callable[[SensorData], None]] = None
        
        # Collision detection
        self._last_distance = float('inf')
        self._collision_threshold = 15.0  # cm - trigger if closer than this
        self._collision_delta_threshold = 20.0  # cm - trigger if distance drops by this much
        self._collision_cooldown = 2.0  # seconds between collision events
        self._last_collision_time = 0
        
    def connect(self) -> bool:
        """Connect to the rover."""
        self.state = RoverState.CONNECTING
        
        try:
            # Command socket
            self._cmd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._cmd_socket.settimeout(5.0)
            self._cmd_socket.connect((self.host, self.CMD_PORT))
            self._cmd_socket.settimeout(None)
            
            # Video socket
            self._video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._video_socket.settimeout(5.0)
            self._video_socket.connect((self.host, self.VIDEO_PORT))
            self._video_socket.settimeout(None)
            
            self._running = True
            
            # Start receiver threads
            self._cmd_thread = threading.Thread(target=self._cmd_receiver, daemon=True)
            self._cmd_thread.start()
            
            self._video_thread = threading.Thread(target=self._video_receiver, daemon=True)
            self._video_thread.start()
            
            self.state = RoverState.CONNECTED
            print(f"✅ Connected to rover at {self.host}")
            return True
            
        except Exception as e:
            self.state = RoverState.ERROR
            print(f"❌ Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the rover."""
        self._running = False
        self.stop()  # Stop motors first
        
        if self._cmd_socket:
            try:
                self._cmd_socket.close()
            except:
                pass
            self._cmd_socket = None
            
        if self._video_socket:
            try:
                self._video_socket.close()
            except:
                pass
            self._video_socket = None
            
        self.state = RoverState.DISCONNECTED
        print("Disconnected from rover")
    
    def _send_cmd(self, cmd: str):
        """Send a command to the rover."""
        if self._cmd_socket and self.state == RoverState.CONNECTED:
            try:
                self._cmd_socket.sendall((cmd + "\n").encode())
            except Exception as e:
                print(f"Error sending command: {e}")
                self.state = RoverState.ERROR
    
    def _cmd_receiver(self):
        """Receive responses from the rover."""
        buffer = ""
        while self._running and self._cmd_socket:
            try:
                data = self._cmd_socket.recv(1024)
                if not data:
                    break
                buffer += data.decode()
                
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self._handle_response(line.strip())
                    
            except Exception as e:
                if self._running:
                    print(f"Command receiver error: {e}")
                break
    
    def _handle_response(self, response: str):
        """Parse response from rover."""
        parts = response.split("#")
        if len(parts) < 2:
            return
            
        cmd = parts[0]
        
        with self._sensor_lock:
            if cmd == "CMD_MODE":
                if parts[1] == "3" and len(parts) >= 3:
                    # Ultrasonic distance
                    try:
                        new_distance = float(parts[2])
                        self._check_collision(new_distance)
                        self.sensors.distance = new_distance
                    except ValueError:
                        pass
                elif parts[1] == "2" and len(parts) >= 4:
                    # Light sensors
                    try:
                        self.sensors.light_left = float(parts[2])
                        self.sensors.light_right = float(parts[3])
                    except ValueError:
                        pass
                elif parts[1] == "4" and len(parts) >= 5:
                    # IR sensors
                    try:
                        self.sensors.ir_left = float(parts[2])
                        self.sensors.ir_center = float(parts[3])
                        self.sensors.ir_right = float(parts[4])
                    except ValueError:
                        pass
            elif cmd == "CMD_POWER" and len(parts) >= 2:
                try:
                    self.sensors.battery = float(parts[1])
                except ValueError:
                    pass
        
        if self._on_sensor_update:
            self._on_sensor_update(self.sensors)
    
    def _check_collision(self, new_distance: float):
        """Check if we hit something."""
        now = time.time()
        
        # Check for sudden distance decrease (impact) or very close proximity
        delta = self._last_distance - new_distance
        is_collision = (
            (delta > self._collision_delta_threshold) or 
            (new_distance < self._collision_threshold and self._last_distance >= self._collision_threshold)
        )
        
        if is_collision and (now - self._last_collision_time) > self._collision_cooldown:
            self._last_collision_time = now
            print(f"💥 COLLISION! Distance dropped from {self._last_distance:.1f} to {new_distance:.1f} cm")
            
            # Stop immediately
            self.stop()
            
            # Trigger callback
            if self._on_collision:
                self._on_collision(new_distance)
        
        self._last_distance = new_distance
    
    def _video_receiver(self):
        """Receive video frames from the rover."""
        while self._running and self._video_socket:
            try:
                # Read 4-byte length prefix
                length_data = self._recv_exact(self._video_socket, 4)
                if not length_data:
                    break
                    
                frame_length = struct.unpack('<I', length_data)[0]
                
                # Read frame data
                frame_data = self._recv_exact(self._video_socket, frame_length)
                if not frame_data:
                    break
                
                with self._frame_lock:
                    self._latest_frame = frame_data
                
                if self._on_frame:
                    self._on_frame(frame_data)
                    
            except Exception as e:
                if self._running:
                    print(f"Video receiver error: {e}")
                break
    
    def _recv_exact(self, sock: socket.socket, length: int) -> Optional[bytes]:
        """Receive exactly `length` bytes."""
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    
    # ========== MOVEMENT COMMANDS ==========
    
    def move(self, fl: int, bl: int, fr: int, br: int):
        """
        Set motor speeds directly.
        
        Args:
            fl: Front-left motor (-4095 to 4095)
            bl: Back-left motor
            fr: Front-right motor
            br: Back-right motor
        """
        # Clamp values
        fl = max(-4095, min(4095, fl))
        bl = max(-4095, min(4095, bl))
        fr = max(-4095, min(4095, fr))
        br = max(-4095, min(4095, br))
        
        self._send_cmd(f"CMD_MOTOR#{fl}#{bl}#{fr}#{br}")
    
    def stop(self):
        """Stop all motors."""
        self.move(0, 0, 0, 0)
    
    def forward(self, speed: int = 2000):
        """Move forward."""
        self.move(speed, speed, speed, speed)
    
    def backward(self, speed: int = 2000):
        """Move backward."""
        self.move(-speed, -speed, -speed, -speed)
    
    def turn_left(self, speed: int = 2000):
        """Spin left in place."""
        self.move(-speed, -speed, speed, speed)
    
    def turn_right(self, speed: int = 2000):
        """Spin right in place."""
        self.move(speed, speed, -speed, -speed)
    
    def strafe_left(self, speed: int = 2000):
        """Strafe left (mecanum wheels only - won't work on this kit)."""
        self.move(-speed, speed, speed, -speed)
    
    def strafe_right(self, speed: int = 2000):
        """Strafe right (mecanum wheels only - won't work on this kit)."""
        self.move(speed, -speed, -speed, speed)
    
    # ========== SERVO (CAMERA TILT) ==========
    
    def set_camera_angle(self, horizontal: int = 90, vertical: int = 90):
        """
        Set camera servo angles.
        
        Args:
            horizontal: 0-180 degrees (90 = center)
            vertical: 0-180 degrees (90 = level)
        """
        self._send_cmd(f"CMD_SERVO#0#{horizontal}")
        self._send_cmd(f"CMD_SERVO#1#{vertical}")
    
    def look_center(self):
        """Center the camera."""
        self.set_camera_angle(90, 90)
    
    def look_left(self):
        """Turn camera left."""
        self.set_camera_angle(135, 90)
    
    def look_right(self):
        """Turn camera right."""
        self.set_camera_angle(45, 90)
    
    # ========== SENSORS ==========
    
    def request_distance(self):
        """Request ultrasonic distance reading."""
        self._send_cmd("CMD_SONIC")
    
    def request_battery(self):
        """Request battery level."""
        self._send_cmd("CMD_POWER")
    
    def request_light(self):
        """Request light sensor readings."""
        self._send_cmd("CMD_LIGHT")
    
    def request_line(self):
        """Request line sensor (IR) readings."""
        self._send_cmd("CMD_LINE")
    
    # ========== LED ==========
    
    def set_led(self, index: int, r: int, g: int, b: int):
        """Set LED color."""
        self._send_cmd(f"CMD_LED#{index}#{r}#{g}#{b}")
    
    def led_mode(self, mode: int):
        """
        Set LED mode.
        0 = off, 1 = manual, 2 = following, 3 = blink, 4 = rainbow breathe, 5 = rainbow cycle
        """
        self._send_cmd(f"CMD_LED_MOD#{mode}")
    
    # ========== BUZZER ==========
    
    def buzzer(self, on: bool):
        """Turn buzzer on/off."""
        self._send_cmd(f"CMD_BUZZER#{1 if on else 0}")
    
    def beep(self, duration: float = 0.1):
        """Quick beep."""
        self.buzzer(True)
        time.sleep(duration)
        self.buzzer(False)
    
    # ========== AUDIO (CUSTOM EXTENSION) ==========
    
    def play_audio(self, filename: str):
        """Play audio file on the rover (requires our server extension)."""
        self._send_cmd(f"CMD_AUDIO#{filename}")
    
    # ========== VIDEO ==========
    
    def get_frame(self) -> Optional[bytes]:
        """Get the latest video frame (JPEG bytes)."""
        with self._frame_lock:
            return self._latest_frame
    
    def get_frame_image(self) -> Optional['Image.Image']:
        """Get the latest frame as a PIL Image."""
        if not HAS_PIL:
            raise ImportError("PIL not installed. Run: pip install Pillow")
        
        frame = self.get_frame()
        if frame:
            return Image.open(io.BytesIO(frame))
        return None
    
    # ========== CALLBACKS ==========
    
    def on_frame(self, callback: Callable[[bytes], None]):
        """Register callback for new video frames."""
        self._on_frame = callback
    
    def on_collision(self, callback: Callable[[float], None]):
        """Register callback for collision events."""
        self._on_collision = callback
    
    def on_sensor_update(self, callback: Callable[[SensorData], None]):
        """Register callback for sensor updates."""
        self._on_sensor_update = callback


# ========== CLI DEMO ==========

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ultron Rover Client")
    parser.add_argument("--host", default="raspberrypi.local", help="Rover hostname/IP")
    parser.add_argument("--demo", action="store_true", help="Run movement demo")
    args = parser.parse_args()
    
    rover = UltronRover(host=args.host)
    
    def on_collision(distance):
        print(f"🔊 Playing collision sound! Distance: {distance:.1f}cm")
        rover.play_audio("ow_1.mp3")
    
    rover.on_collision(on_collision)
    
    if rover.connect():
        print("\nRover connected! Commands:")
        print("  w/a/s/d - move")
        print("  q - quit")
        print("  space - stop")
        
        if args.demo:
            print("\nRunning demo sequence...")
            time.sleep(1)
            
            rover.forward(1500)
            time.sleep(1)
            
            rover.stop()
            time.sleep(0.5)
            
            rover.turn_right(1500)
            time.sleep(0.5)
            
            rover.stop()
            time.sleep(0.5)
            
            rover.backward(1500)
            time.sleep(1)
            
            rover.stop()
            print("Demo complete!")
        else:
            # Simple keyboard control
            try:
                import sys
                import tty
                import termios
                
                old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                
                speed = 2000
                
                print("\nReady for input...")
                while True:
                    char = sys.stdin.read(1)
                    
                    if char == 'q':
                        break
                    elif char == 'w':
                        rover.forward(speed)
                    elif char == 's':
                        rover.backward(speed)
                    elif char == 'a':
                        rover.turn_left(speed)
                    elif char == 'd':
                        rover.turn_right(speed)
                    elif char == ' ':
                        rover.stop()
                    elif char == '+':
                        speed = min(4095, speed + 500)
                        print(f"Speed: {speed}")
                    elif char == '-':
                        speed = max(500, speed - 500)
                        print(f"Speed: {speed}")
                
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                
            except ImportError:
                print("Keyboard control not available on this platform")
                input("Press Enter to disconnect...")
        
        rover.disconnect()
