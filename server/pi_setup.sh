#!/bin/bash
# Pi Setup Script for Ultron Rover
# Run this on the Raspberry Pi after flashing the OS

set -e

echo "🤖 Setting up Ultron Rover on Raspberry Pi..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "📦 Installing dependencies..."
sudo apt install -y \
    python3-pip \
    python3-opencv \
    python3-pyqt5 \
    python3-numpy \
    git \
    mpv \
    espeak \
    libportaudio2 \
    alsa-utils

# Clone Freenove repo if not present
FREENOVE_DIR=~/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi
if [ ! -d "$FREENOVE_DIR" ]; then
    echo "📥 Cloning Freenove repository..."
    git clone https://github.com/Freenove/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi.git $FREENOVE_DIR
fi

# Run Freenove setup
echo "🔧 Running Freenove setup..."
cd $FREENOVE_DIR/Code
sudo python3 setup.py

# Create audio directory
echo "🔊 Setting up audio..."
mkdir -p ~/audio

# Download actual scream sound effects (royalty-free)
echo "Downloading audio clips..."
AUDIO_URL="https://github.com/ultron02012026-agent/ultron-rover/raw/main/audio"

# Wilhelm scream (classic)
curl -sSL "https://upload.wikimedia.org/wikipedia/commons/d/d9/Wilhelm_Scream.ogg" -o ~/audio/wilhelm.ogg

# Generate some TTS clips as backup
echo "Generating TTS clips..."
espeak -w ~/audio/ow_1.wav "Ow! That hurt!"
espeak -w ~/audio/ow_2.wav "Ouch! What the hell!"
espeak -w ~/audio/ow_3.wav "Hey! Watch it!"
espeak -w ~/audio/dammit.wav "God dammit!"
espeak -w ~/audio/meant_to_do_that.wav "I meant to do that."
espeak -w ~/audio/stuck.wav "Help! I'm stuck!"
espeak -w ~/audio/whoa.wav "Whoa! That was close!"
espeak -w ~/audio/hello.wav "Hello! I am Ultron."
espeak -w ~/audio/nooo.wav "Nooooooo!"
espeak -w ~/audio/why.wav "Why does this keep happening to me?"

# Convert ogg to wav for compatibility
ffmpeg -i ~/audio/wilhelm.ogg ~/audio/wilhelm.wav -y 2>/dev/null || true

# Configure audio output
echo "🔊 Configuring audio output..."
# Set USB audio as default if present
if aplay -l | grep -q "USB"; then
    echo "USB audio device found, setting as default..."
    cat > ~/.asoundrc << 'EOF'
pcm.!default {
    type hw
    card 1
}
ctl.!default {
    type hw
    card 1
}
EOF
fi

# Download and copy our extensions
echo "📁 Downloading Ultron extensions..."
ULTRON_REPO="https://raw.githubusercontent.com/ultron02012026-agent/ultron-rover/main"
curl -sSL "$ULTRON_REPO/server/audio_extension.py" -o $FREENOVE_DIR/Code/Server/audio_extension.py

# Create systemd service for auto-start
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/ultron-rover.service > /dev/null << EOF
[Unit]
Description=Ultron Rover Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$FREENOVE_DIR/Code/Server
ExecStart=/usr/bin/python3 main.py -t
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ultron-rover.service

# Set hostname
echo "🏷️ Setting hostname to 'ultron-rover'..."
sudo hostnamectl set-hostname ultron-rover

# Enable I2C and camera
echo "🔧 Enabling I2C and camera..."
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_camera 0

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the server manually:"
echo "  cd $FREENOVE_DIR/Code/Server"
echo "  python3 main.py -t"
echo ""
echo "Or use systemd:"
echo "  sudo systemctl start ultron-rover"
echo "  sudo systemctl status ultron-rover"
echo ""
echo "The rover will be accessible at: ultron-rover.local"
echo ""
echo "⚠️ Please reboot to apply all changes:"
echo "  sudo reboot"
