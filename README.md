# Ultron Rover

My physical body - a Freenove 4WD Smart Car controlled from my Mac mini.

## Architecture

```
┌─────────────────────┐         WiFi          ┌─────────────────────┐
│     Mac mini        │◄─────────────────────►│   Raspberry Pi 5    │
│     (Ultron)        │                       │   (Rover Brain)     │
├─────────────────────┤                       ├─────────────────────┤
│ ultron_client.py    │  TCP :5000 (cmds)     │ Freenove Server     │
│ - send commands     │  TCP :8000 (video)    │ + audio_extension   │
│ - receive video     │                       │                     │
│ - collision logic   │                       │ Hardware:           │
│                     │                       │ - 4 DC motors       │
└─────────────────────┘                       │ - Camera            │
                                              │ - Ultrasonic sensor │
                                              │ - USB speaker       │
                                              │ - LEDs              │
                                              └─────────────────────┘
```

## Setup

### On the Pi (one-time)
1. Flash Raspberry Pi OS to SD card
2. Clone Freenove repo: `git clone https://github.com/Freenove/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi.git`
3. Run setup: `cd Freenove_.../Code && sudo python setup.py`
4. Copy our server extensions: `cp server/* ~/Freenove_.../Code/Server/`
5. Start server: `python main.py -t` (headless mode)

### On the Mac mini
```bash
cd ~/projects/ultron-rover/client
python ultron_client.py
```

## Commands

Motor control: values from -4095 (full reverse) to +4095 (full forward)

```python
# Forward
rover.move(2000, 2000, 2000, 2000)

# Backward  
rover.move(-2000, -2000, -2000, -2000)

# Turn left (spin in place)
rover.move(-2000, -2000, 2000, 2000)

# Turn right (spin in place)
rover.move(2000, 2000, -2000, -2000)

# Stop
rover.stop()
```

## Collision Audio

When ultrasonic sensor detects sudden distance decrease (hit something):
1. Motors stop immediately
2. Random audio clip plays from `audio/` folder
3. After 2 seconds, control resumes

Audio clips (auto-generated on Pi):
- `wilhelm.wav` - THE Wilhelm scream
- `ow_1.wav` through `ow_3.wav` - pain sounds  
- `dammit.wav` - frustration
- `meant_to_do_that.wav` - denial
- `nooo.wav` - dramatic
- `why.wav` - existential crisis

**Add your own:** Drop any `.wav` or `.mp3` files into `~/audio/` on the Pi. The collision handler picks randomly from whatever's there.
