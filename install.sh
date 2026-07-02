#!/data/data/com.termux/files/usr/bin/bash

# Colors for a nice interface
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BLUE}${BOLD}🎵 mplay - Installer${NC}"
echo -e "${CYAN}Preparing to install dependencies...${NC}\n"

# Function to show a progress bar
show_progress() {
    local duration=$1
    local label=$2
    local columns=$(tput cols)
    local bar_width=$((columns - 25))
    if [ $bar_width -lt 10 ]; then bar_width=10; fi

    echo -ne "${label}\n"
    for ((i=0; i<=100; i+=2)); do
        local filled=$((i * bar_width / 100))
        local empty=$((bar_width - filled))
        printf "\r\033[K${CYAN}[${BLUE}"
        printf "%${filled}s" | tr ' ' '█'
        printf "${NC}"
        printf "%${empty}s" | tr ' ' '░'
        printf "${CYAN}] ${i}%%"
        sleep 0.05
    done
    echo -e "\n"
}

# 1. Update and install system packages
echo -e "${BOLD}[1/5] Installing System Packages (mpv, python)...${NC}"
pkg update -y && pkg install -y mpv python ffmpeg-python
if ! command -v mpv >/dev/null 2>&1; then
    echo -e "${RED}✗ mpv failed to install. mplay needs mpv to play anything.${NC}"
    echo -e "  Try running: ${CYAN}pkg install mpv${NC} manually and re-run this script."
    exit 1
fi
show_progress 1 "System updates and core packages..."

# 2. Install Python libraries
echo -e "${BOLD}[2/5] Installing Python Libraries (blessed)...${NC}"
pip install blessed
if ! python3 -c "import blessed" >/dev/null 2>&1; then
    echo -e "${RED}✗ the 'blessed' Python library failed to install.${NC}"
    echo -e "  Try running: ${CYAN}pip install blessed${NC} manually and re-run this script."
    exit 1
fi
show_progress 1 "Python dependencies..."

# 3. Setting up Alias
echo -e "${BOLD}[3/5] Setting up 'mplay' alias...${NC}"
SCRIPT_PATH=$(realpath mplay.py)

# Detect Shell and apply alias
if [[ $SHELL == *"fish"* ]]; then
    alias -s mplay "python3 $SCRIPT_PATH"
    funcsave mplay > /dev/null 2>&1
else
    # Default to Bash/Zsh
    echo "alias mplay='python3 $SCRIPT_PATH'" >> ~/.bashrc
    source ~/.bashrc > /dev/null 2>&1
fi
show_progress 0.5 "Configuration and shortcuts..."

# 4. Check Termux volume-key behaviour
# mplay controls mpv's software volume with +/- inside the app, but the physical
# volume rocker only reaches mpv if Termux hasn't repurposed it for special keys.
echo -e "${BOLD}[4/5] Checking Termux volume key behavior...${NC}"
PROP_FILE="$HOME/.termux/termux.properties"
if [ -f "$PROP_FILE" ] && grep -qE '^[[:space:]]*volume-keys[[:space:]]*=[[:space:]]*special-keys' "$PROP_FILE"; then
    echo -e "${RED}⚠ Your Termux volume keys are set to 'special-keys' mode.${NC}"
    echo -e "  That means the volume rocker won't adjust mpv/media volume."
    echo -e "  Open ${CYAN}$PROP_FILE${NC}, remove or comment out the 'volume-keys' line,"
    echo -e "  then run ${CYAN}termux-reload-settings${NC} to restore normal volume control."
    echo -e "  (You can still use ${CYAN}+${NC} / ${CYAN}-${NC} inside mplay to change volume either way.)"
else
    echo -e "${GREEN}✓ Volume keys look normal — the hardware rocker should control mpv's volume.${NC}"
    echo -e "  You can also use ${CYAN}+${NC} / ${CYAN}-${NC} inside mplay for volume control."
fi

# 5. PulseAudio + cava (optional — mplay works fine without this, it just enables
# routing audio through pulse so a `cava` session can visualize it)
echo -e "${BOLD}[5/5] Setting up audio visualizer support (pulseaudio, cava)...${NC}"
pkg install -y pulseaudio cava
if command -v pulseaudio >/dev/null 2>&1 && command -v cava >/dev/null 2>&1; then
    pulseaudio --start --exit-idle-time=-1 >/dev/null 2>&1
    sleep 2
    SINK_NAME=$(pactl list sinks short 2>/dev/null | awk '$2 != "auto_null" {print $2; exit}')
    mkdir -p ~/.config/cava
    if [ -n "$SINK_NAME" ] && [ ! -f ~/.config/cava/config ]; then
        cat > ~/.config/cava/config <<EOF
[input]
method = pulse
source = ${SINK_NAME}.monitor
EOF
        echo -e "${GREEN}✓ cava configured automatically to visualize ${SINK_NAME}.${NC}"
    elif [ -f ~/.config/cava/config ]; then
        echo -e "${GREEN}✓ cava already has a config — leaving it as-is.${NC}"
    else
        echo -e "${YELLOW}⚠ Couldn't detect a real audio sink yet (normal on a first-ever install).${NC}"
        echo -e "  Run mplay once, play any track, then in another session run:"
        echo -e "  ${CYAN}pactl list sinks short${NC} — note the sink name, then edit"
        echo -e "  ${CYAN}~/.config/cava/config${NC} and set: source = <sink-name>.monitor"
    fi
    echo -e "${GREEN}✓ pulseaudio + cava installed. mplay routes audio through pulse automatically —${NC}"
    echo -e "  just run ${CYAN}mplay${NC} normally, then ${CYAN}cava${NC} in a second Termux session to visualize.${NC}"
else
    echo -e "${YELLOW}⚠ pulseaudio/cava couldn't be installed — mplay still works completely fine,${NC}"
    echo -e "  it'll just use normal audio output without visualizer support.${NC}"
fi
show_progress 0.5 "Visualizer support..."

echo -e "${GREEN}${BOLD}✨ ALL DEPENDENCIES INSTALLED SUCCESSFULLY!${NC}"
echo -e "----------------------------------------------------"
echo -e "${BOLD}🚀 How to run:${NC}"
echo -e "1. Simply type ${CYAN}mplay${NC} anywhere in your terminal."
echo -e "2. Run manually with: ${CYAN}python3 mplay.py${NC}"
echo -e "3. Browse files by typing: ${CYAN}mplay ~/your/music/folder${NC}"
echo -e "----------------------------------------------------"
echo -e "${YELLOW}Note: Make sure you have a Nerd Font installed in Termux"
echo -e "to see all the icons correctly!${NC}"
