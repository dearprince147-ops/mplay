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
echo -e "${BOLD}[1/4] Installing System Packages (mpv, python)...${NC}"
pkg update -y && pkg install -y mpv python ffmpeg-python
if ! command -v mpv >/dev/null 2>&1; then
    echo -e "${RED}✗ mpv failed to install. mplay needs mpv to play anything.${NC}"
    echo -e "  Try running: ${CYAN}pkg install mpv${NC} manually and re-run this script."
    exit 1
fi
show_progress 1 "System updates and core packages..."

# 2. Install Python libraries
echo -e "${BOLD}[2/4] Installing Python Libraries (blessed)...${NC}"
pip install blessed
if ! python3 -c "import blessed" >/dev/null 2>&1; then
    echo -e "${RED}✗ the 'blessed' Python library failed to install.${NC}"
    echo -e "  Try running: ${CYAN}pip install blessed${NC} manually and re-run this script."
    exit 1
fi
show_progress 1 "Python dependencies..."

# 3. Setting up Alias
echo -e "${BOLD}[3/4] Setting up 'mplay' alias...${NC}"
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
echo -e "${BOLD}[4/4] Checking Termux volume key behavior...${NC}"
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

echo -e "${GREEN}${BOLD}✨ ALL DEPENDENCIES INSTALLED SUCCESSFULLY!${NC}"
echo -e "----------------------------------------------------"
echo -e "${BOLD}🚀 How to run:${NC}"
echo -e "1. Simply type ${CYAN}mplay${NC} anywhere in your terminal."
echo -e "2. Run manually with: ${CYAN}python3 mplay.py${NC}"
echo -e "3. Browse files by typing: ${CYAN}mplay ~/your/music/folder${NC}"
echo -e "----------------------------------------------------"
echo -e "${YELLOW}Note: Make sure you have a Nerd Font installed in Termux"
echo -e "to see all the icons correctly!${NC}"
