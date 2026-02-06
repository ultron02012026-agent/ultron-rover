#!/usr/bin/env python3
"""
Rover API - High-level interface for Ultron to control the rover.

This provides simple functions I can call from OpenClaw to control my body.
"""

import time
import base64
import io
from typing import Optional, Tuple
from pathlib import Path

from ultron_client import UltronRover, SensorData

# Global rover instance
_rover: Optional[UltronRover] = None


def connect(host: str = "raspberrypi.local") -> bool:
    """Connect to the rover. Returns True on success."""
    global _rover
    if _rover and _rover.state.value == "connected":
        return True
    
    _rover = UltronRover(host=host)
    
    # Set up collision handler
    def on_collision(distance):
        print(f"💥 COLLISION at {distance:.1f}cm - playing audio")
        _rover.play_audio("ow_random")  # Server picks random ow clip
    
    _rover.on_collision(on_collision)
    
    return _rover.connect()


def disconnect():
    """Disconnect from the rover."""
    global _rover
    if _rover:
        _rover.disconnect()
        _rover = None


def is_connected() -> bool:
    """Check if connected to rover."""
    return _rover is not None and _rover.state.value == "connected"


# ========== MOVEMENT ==========

def forward(speed: int = 2000, duration: float = 0):
    """
    Move forward.
    
    Args:
        speed: 0-4095 (default 2000 is moderate)
        duration: If > 0, move for this many seconds then stop
    """
    if not is_connected():
        return "Not connected to rover"
    
    _rover.forward(speed)
    
    if duration > 0:
        time.sleep(duration)
        _rover.stop()
        return f"Moved forward for {duration}s"
    
    return "Moving forward"


def backward(speed: int = 2000, duration: float = 0):
    """Move backward."""
    if not is_connected():
        return "Not connected to rover"
    
    _rover.backward(speed)
    
    if duration > 0:
        time.sleep(duration)
        _rover.stop()
        return f"Moved backward for {duration}s"
    
    return "Moving backward"


def turn_left(speed: int = 2000, duration: float = 0):
    """Spin left in place."""
    if not is_connected():
        return "Not connected to rover"
    
    _rover.turn_left(speed)
    
    if duration > 0:
        time.sleep(duration)
        _rover.stop()
        return f"Turned left for {duration}s"
    
    return "Turning left"


def turn_right(speed: int = 2000, duration: float = 0):
    """Spin right in place."""
    if not is_connected():
        return "Not connected to rover"
    
    _rover.turn_right(speed)
    
    if duration > 0:
        time.sleep(duration)
        _rover.stop()
        return f"Turned right for {duration}s"
    
    return "Turning right"


def stop():
    """Stop all movement."""
    if not is_connected():
        return "Not connected to rover"
    
    _rover.stop()
    return "Stopped"


def move(fl: int, bl: int, fr: int, br: int):
    """
    Direct motor control.
    
    Args:
        fl: Front-left motor (-4095 to 4095)
        bl: Back-left motor
        fr: Front-right motor  
        br: Back-right motor
    """
    if not is_connected():
        return "Not connected to rover"
    
    _rover.move(fl, bl, fr, br)
    return f"Motors set to FL={fl}, BL={bl}, FR={fr}, BR={br}"


# ========== CAMERA ==========

def look(direction: str = "center"):
    """
    Point the camera.
    
    Args:
        direction: "left", "right", "center", "up", "down"
    """
    if not is_connected():
        return "Not connected to rover"
    
    if direction == "left":
        _rover.look_left()
    elif direction == "right":
        _rover.look_right()
    elif direction == "center":
        _rover.look_center()
    elif direction == "up":
        _rover.set_camera_angle(90, 45)
    elif direction == "down":
        _rover.set_camera_angle(90, 135)
    else:
        return f"Unknown direction: {direction}"
    
    return f"Looking {direction}"


def get_camera_frame() -> Optional[bytes]:
    """Get current camera frame as JPEG bytes."""
    if not is_connected():
        return None
    return _rover.get_frame()


def get_camera_base64() -> Optional[str]:
    """Get current camera frame as base64-encoded JPEG."""
    frame = get_camera_frame()
    if frame:
        return base64.b64encode(frame).decode()
    return None


def save_camera_frame(path: str = "/tmp/rover_frame.jpg") -> str:
    """Save current camera frame to file."""
    frame = get_camera_frame()
    if not frame:
        return "No frame available"
    
    Path(path).write_bytes(frame)
    return f"Saved frame to {path}"


# ========== SENSORS ==========

def get_distance() -> float:
    """Get ultrasonic distance in cm."""
    if not is_connected():
        return -1
    
    _rover.request_distance()
    time.sleep(0.1)  # Wait for response
    return _rover.sensors.distance


def get_battery() -> float:
    """Get battery voltage."""
    if not is_connected():
        return -1
    
    _rover.request_battery()
    time.sleep(0.1)
    return _rover.sensors.battery


def get_sensors() -> dict:
    """Get all sensor readings."""
    if not is_connected():
        return {"error": "Not connected"}
    
    # Request all sensors
    _rover.request_distance()
    _rover.request_battery()
    _rover.request_light()
    _rover.request_line()
    time.sleep(0.2)
    
    s = _rover.sensors
    return {
        "distance_cm": s.distance,
        "battery_v": s.battery,
        "light_left": s.light_left,
        "light_right": s.light_right,
        "ir_left": s.ir_left,
        "ir_center": s.ir_center,
        "ir_right": s.ir_right,
    }


# ========== LED ==========

def set_led_color(r: int, g: int, b: int, index: int = 0x00):
    """
    Set LED color.
    
    Args:
        r, g, b: 0-255
        index: LED index (0x00 = all, or specific LED number)
    """
    if not is_connected():
        return "Not connected"
    
    _rover.set_led(index, r, g, b)
    return f"LED set to RGB({r}, {g}, {b})"


def led_off():
    """Turn off LEDs."""
    if not is_connected():
        return "Not connected"
    
    _rover.led_mode(0)
    return "LEDs off"


def led_rainbow():
    """Enable rainbow LED mode."""
    if not is_connected():
        return "Not connected"
    
    _rover.led_mode(5)
    return "Rainbow mode enabled"


# ========== AUDIO ==========

def play_sound(filename: str):
    """Play audio file on the rover."""
    if not is_connected():
        return "Not connected"
    
    _rover.play_audio(filename)
    return f"Playing {filename}"


def beep(duration: float = 0.1):
    """Quick beep."""
    if not is_connected():
        return "Not connected"
    
    _rover.beep(duration)
    return "Beeped"


# ========== COMPOUND ACTIONS ==========

def explore(duration: float = 10):
    """
    Autonomous exploration for a given duration.
    
    Drives forward, avoids obstacles, looks around.
    """
    if not is_connected():
        return "Not connected"
    
    start = time.time()
    print(f"🔍 Exploring for {duration}s...")
    
    while time.time() - start < duration:
        # Check distance
        dist = get_distance()
        
        if dist < 30:
            # Obstacle ahead - turn
            stop()
            time.sleep(0.2)
            
            # Look around to decide
            look("left")
            time.sleep(0.3)
            left_dist = get_distance()
            
            look("right")
            time.sleep(0.3)
            right_dist = get_distance()
            
            look("center")
            
            if left_dist > right_dist:
                turn_left(1500, 0.3)
            else:
                turn_right(1500, 0.3)
        else:
            # Path clear - go forward
            forward(1500)
        
        time.sleep(0.1)
    
    stop()
    return f"Explored for {duration}s"


def patrol(waypoints: list = None):
    """
    Patrol a series of movements.
    
    Args:
        waypoints: List of (action, duration) tuples
                   e.g., [("forward", 2), ("turn_left", 0.5), ("forward", 1)]
    """
    if not is_connected():
        return "Not connected"
    
    if not waypoints:
        # Default patrol pattern
        waypoints = [
            ("forward", 1.5),
            ("turn_right", 0.4),
            ("forward", 1.5),
            ("turn_right", 0.4),
            ("forward", 1.5),
            ("turn_right", 0.4),
            ("forward", 1.5),
            ("turn_right", 0.4),
        ]
    
    actions = {
        "forward": forward,
        "backward": backward,
        "turn_left": turn_left,
        "turn_right": turn_right,
        "stop": lambda d: stop() or time.sleep(d),
    }
    
    for action, duration in waypoints:
        if action in actions:
            actions[action](duration=duration)
        time.sleep(0.1)
    
    stop()
    return "Patrol complete"


# ========== STATUS ==========

def status() -> dict:
    """Get rover status."""
    return {
        "connected": is_connected(),
        "host": _rover.host if _rover else None,
        "state": _rover.state.value if _rover else "disconnected",
        "sensors": get_sensors() if is_connected() else None,
    }


# CLI for testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = "raspberrypi.local"
    
    print(f"Connecting to {host}...")
    if connect(host):
        print("Connected!")
        print(f"Status: {status()}")
        
        print("\nTesting movements...")
        forward(1500, 0.5)
        time.sleep(0.2)
        turn_right(1500, 0.3)
        time.sleep(0.2)
        backward(1500, 0.5)
        stop()
        
        print("\nDone!")
        disconnect()
    else:
        print("Failed to connect")
