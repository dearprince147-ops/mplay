# 🎵 mplay

A minimalist, high-performance terminal music player and file explorer designed specifically for **Termux** and low-resource environments. Built with a sleek **Nerd Font** interface and powered by `mpv`.

![mplay Screenshot Placeholder](https://raw.githubusercontent.com/username/repo/main/screenshot.png)

## ✨ Features

- **📂 Integrated File Explorer:** Navigate your entire storage from the CLI. Starts at `~/` by default.
- **🔍 Real-time Search:** Instantly filter folders and music files as you type.
- **🎨 Modern TUI:** Sleek blue-themed progress bars and vibrant, adaptive shortcut legends.
- **⚡ Intuitive Controls:** Optimized for one-handed navigation in Termux using arrow keys.
- **🎧 Auto-Advance:** Plays through your entire folder or filtered search results automatically.
- **🛡️ Robust & Stable:** Built with `blessed` to handle terminal quirks and resizing gracefully.

## 🚀 Installation (Automated)

The easiest way to install everything is using the provided `install.sh` script.

```bash
chmod +x install.sh
./install.sh
```

**The installer will automatically:**
1. Update your system.
2. Install **System Packages:** `mpv`, `python`.
3. Install **Python Libraries:** `blessed`.
4. Set up the `mplay` **terminal shortcut/alias**.

### 🎨 Nerd Fonts
To see the icons correctly, ensure you have a [Nerd Font](https://www.nerdfonts.com/) installed in your terminal emulator (like Termux-Styling).

## ⏩ Shortcuts & Accessibility

### 1. Terminal Command
After running `install.sh`, you can launch the app from anywhere by simply typing:
```bash
mplay
```

### 2. Termux Widget (Home Screen Icon)
If you have the [Termux:Widget](https://github.com/termux/termux-widget) app installed:
1. Create the shortcuts directory: `mkdir -p ~/.shortcuts`
2. Copy the widget script: `cp mplay.sh ~/.shortcuts/`
3. Make it executable: `chmod +x ~/.shortcuts/mplay.sh`
4. Now, add the Termux Widget to your Android home screen and select `mplay.sh` to launch it instantly!

## 🎮 How to Use

Launch from anywhere:
```bash
mplay
```
Or browse a specific folder directly:
```bash
mplay ~/storage/shared/Music/
```

### Keyboard Shortcuts

#### 📂 Explorer Mode (Browsing)
- **↑ / ↓**: Navigate list
- **→ / ENTER**: Open Folder / Play Song
- **←**: Go Back to parent folder
- **Type anything**: Start searching/filtering
- **BACKSPACE**: Clear search character / Go Back (if search is empty)
- **ESC**: Clear full search

#### 🎵 Player Mode (Listening)
- **SPACE**: Toggle Play/Pause
- **N**: Next track
- **P**: Previous track
- **S**: Stop playback
- **Q**: Quit Application

## 🛠️ Technical Specs
- **Backend Player:** `mpv` (System Package)
- **Primary Library:** `blessed` (Python Library)
- **Dependency Management:** `install.sh`
- **Icon Set:** Nerd Font (v3.0+)

---
*Built with ❤️ for the Termux community.*
