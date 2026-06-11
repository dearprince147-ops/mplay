#!/usr/bin/env python3
"""
mplay  ·  terminal music player  (Nerd Font edition)
deps : mpv, blessed
usage: python mplay.py [directory]
"""

import sys, subprocess, threading, time, json, socket, os
from pathlib import Path
from blessed import Terminal

# ── Nerd Font icons ───────────────────────────────────────────────────────────
I_PLAY   = "\uf04b"
I_PAUSE  = "\uf04c"
I_STOP   = "\uf04d"
I_NEXT   = "\uf04e"
I_PREV   = "\uf04a"
I_NOTE   = "\U000f0386"
I_MUSIC  = "\uf001"
I_FOLDER = "\uf07b"
I_TRACK  = "\U000f033c"
I_CLOCK  = "\uf017"
I_DISC   = "\uf51f"
I_SEARCH = "\uf002"
I_DIR    = "\uf07b"
I_UP     = "\uf062"

EXT_ICON = {
    ".mp3": "\uf1c7", ".flac": "\U000f059e", ".ogg": "\U000f0386",
    ".wav": "\U000f033c", ".m4a": "\uf1c7", ".aac": "\uf1c7",
    ".opus": "\U000f0386", ".wma": "\uf1c7", ".ape": "\U000f059e", ".alac": "\U000f059e",
}
AUDIO = set(EXT_ICON.keys())

# ── Helpers ───────────────────────────────────────────────────────────────────
def ftime(s: float) -> str:
    if s <= 0: return "--:--"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

def scan(d: str) -> list[Path]:
    p = Path(d).expanduser().resolve()
    if not p.is_dir(): return []
    try:
        dirs = sorted([f for f in p.iterdir() if f.is_dir() and not f.name.startswith('.')], key=lambda f: f.name.lower())
        files = sorted([f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO], key=lambda f: f.name.lower())
    except PermissionError:
        return []
    return dirs + files

# ── player ────────────────────────────────────────────────────────────────────
class Player:
    def __init__(self):
        self.idx:      int | None = None
        self.track:    Path | None = None
        self.proc:     subprocess.Popen | None = None
        self.elapsed:  float = 0.0
        self.duration: float = 0.0
        self.paused:   bool = False
        self.ipc_path: str = "/data/data/com.termux/files/usr/tmp/mplay_mpv.sock"
        self._tick_stop = threading.Event()

    def _get_ipc(self, command):
        if not os.path.exists(self.ipc_path): return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.02)
                s.connect(self.ipc_path)
                s.sendall((json.dumps({"command": command}) + "\n").encode())
                res = s.recv(1024).decode()
                return json.loads(res.split('\n')[0]).get("data")
        except: return None

    def toggle_pause(self):
        if self.proc:
            self.paused = not self.paused
            self._get_ipc(["set_property", "pause", self.paused])

    def play(self, track: Path, idx: int):
        self._kill()
        self.idx = idx; self.track = track; self.elapsed = 0.0; self.duration = 0.0; self.paused = False
        try:
            os.makedirs(os.path.dirname(self.ipc_path), exist_ok=True)
            self.proc = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet", f"--input-ipc-server={self.ipc_path}", str(track)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._tick_stop.clear()
            threading.Thread(target=self._tick, daemon=True).start()
        except: self.idx = None

    def _tick(self):
        while not self._tick_stop.is_set():
            time.sleep(0.5)
            if self.proc and self.proc.poll() is None:
                curr = self._get_ipc(["get_property", "time-pos"])
                dur = self._get_ipc(["get_property", "duration"])
                if curr is not None: self.elapsed = float(curr)
                if dur is not None: self.duration = float(dur)

    def _kill(self):
        self._tick_stop.set()
        if self.proc:
            try: self.proc.terminate(); self.proc.wait(timeout=0.5)
            except: pass
            self.proc = None
        if os.path.exists(self.ipc_path):
            try: os.remove(self.ipc_path)
            except: pass

    def stop(self): self._kill(); self.idx = None
    def alive(self): return bool(self.proc and self.proc.poll() is None)
    def finished(self): return self.proc is not None and self.proc.poll() is not None

# ── UI ────────────────────────────────────────────────────────────────────────
def draw_ui(term, tracks, player, sel_idx, search_query, offset, directory):
    h, w = term.height, term.width
    out = [term.home + term.clear]
    path_obj = Path(directory).expanduser().resolve()
    home = str(Path.home())
    display_dir = str(path_obj).replace(home, "~", 1) if str(path_obj).startswith(home) else str(path_obj)
    
    # Title
    out.append(term.move_y(0) + term.center(term.bold_blue(f"{I_MUSIC}  M P L A Y")))
    
    # Search
    search_bar = f" {I_SEARCH} Search: {search_query}"
    if not search_query: search_bar += term.gray(" (type to search)")
    out.append(term.move(2, 2) + term.bold_cyan(search_bar[:w-4]))

    # Sub-header
    music_files = [t for t in tracks if t.is_file()]
    left_sub = f"{I_FOLDER} {display_dir}"
    right_sub = f"({len(music_files)} tracks)"
    spaces = max(1, (w-4) - len(left_sub) - len(right_sub))
    out.append(term.move(3, 2) + term.gray(f"{left_sub}{' ' * spaces}{right_sub}"))

    list_h = h - 10
    display_tracks = tracks[offset : offset + list_h]
    
    if not tracks and not search_query:
        out.append(term.move(5 + (list_h//2), 0) + term.center(term.red("Selected directory has no music files!")))
    else:
        for i, item in enumerate(display_tracks):
            abs_i = i + offset
            is_sel = (abs_i == sel_idx)
            is_playing = (player.idx is not None and item == player.track)
            
            if item.is_dir():
                icon = I_DIR; name = item.name + "/"
            else:
                icon = EXT_ICON.get(item.suffix.lower(), I_NOTE); name = item.stem
            
            prefix = f"{I_PAUSE if (is_playing and player.paused) else (I_PLAY if is_playing else ' ')} "
            line = f"{prefix}{abs_i+1:>3} {icon} {name}"
            line = line[:w-6].ljust(w-4)
            
            if is_sel:
                out.append(term.move(5 + i, 2) + term.on_blue(term.white(line)))
            elif item.is_dir():
                out.append(term.move(5 + i, 2) + term.yellow(line))
            elif is_playing:
                out.append(term.move(5 + i, 2) + term.blue(line))
            else:
                out.append(term.move(5 + i, 2) + line)

    # Now Playing
    if player.idx is not None:
        np_y = h - 4
        track, el, dur = player.track, player.elapsed, player.duration
        ratio = (el / dur) if dur > 0 else 0.0
        bar_w = w - 24
        filled = int(bar_w * ratio)
        status = I_PAUSE if player.paused else I_PLAY
        out.append(term.move(np_y, 2) + term.bold_blue(f"{status} {track.stem[:w-10]}"))
        bar = term.blue("█" * filled) + term.gray("░" * (bar_w - filled))
        out.append(term.move(np_y + 1, 2) + f"  {ftime(el)} {bar} {ftime(dur)}")

    # Dynamic Footer Tutorial
    if player.idx is not None:
        # Player Mode Footer
        help_keys = [
            ("SPC", "Play/Pause", term.magenta),
            ("N/P", "Skip", term.blue),
            ("S", "Stop", term.red),
            ("↑↓", "Nav", term.yellow),
            ("←", "Back", term.gray),
            ("Q", "Quit", term.white)
        ]
    else:
        # Explorer Mode Footer
        help_keys = [
            ("←", "Back", term.gray),
            ("→/ENT", "Open", term.cyan),
            ("↑↓", "Nav", term.yellow),
            ("Q", "Quit", term.white)
        ]
        
    help_line = "".join([f"{term.bold(k)} {col(v)}   " for k, v, col in help_keys])
    out.append(term.move(h-1, 0) + term.center(help_line.strip()))
    
    sys.stdout.write("".join(out))
    sys.stdout.flush()

def main():
    term = Terminal()
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1]).expanduser().resolve()
        current_dir = str(target_dir) if target_dir.is_dir() else str(Path.home())
    else:
        current_dir = str(Path.home())
    
    player = Player()
    sel_idx, offset, search_query = 0, 0, ""
    
    def reload_dir(new_dir):
        nonlocal current_dir, sel_idx, offset, search_query
        current_dir = str(new_dir)
        entries = scan(current_dir)
        sel_idx, offset, search_query = 0, 0, ""
        return entries, entries

    all_entries = scan(current_dir)
    filtered_entries = all_entries

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            h, w, list_h = term.height, term.width, term.height - 10
            
            if player.finished():
                files = [t for t in filtered_entries if t.is_file()]
                if player.track in files:
                    curr_f_idx = files.index(player.track)
                    player.play(files[(curr_f_idx + 1) % len(files)], (curr_f_idx + 1) % len(files))
                else: player.stop()

            draw_ui(term, filtered_entries, player, sel_idx, search_query, offset, current_dir)
            key = term.inkey(timeout=0.5)
            if not key: continue

            if key.code == term.KEY_UP:
                sel_idx = max(0, sel_idx - 1)
                if sel_idx < offset: offset = sel_idx
            elif key.code == term.KEY_DOWN:
                sel_idx = min(len(filtered_entries) - 1, sel_idx + 1)
                if sel_idx >= offset + list_h: offset = sel_idx - list_h + 1
            elif key.code == term.KEY_LEFT:
                parent = Path(current_dir).parent
                if parent != Path(current_dir):
                    all_entries, filtered_entries = reload_dir(parent)
            elif key.code == term.KEY_RIGHT or key.code == term.KEY_ENTER or key == "\n":
                if filtered_entries:
                    selected = filtered_entries[sel_idx]
                    if selected.is_dir():
                        all_entries, filtered_entries = reload_dir(selected)
                    else:
                        player.play(selected, sel_idx)
            elif key == " ":
                player.toggle_pause()
            elif key.code == term.KEY_BACKSPACE:
                if search_query:
                    search_query = search_query[:-1]
                    filtered_entries = [t for t in all_entries if search_query.lower() in t.name.lower()]
                else:
                    parent = Path(current_dir).parent
                    if parent != Path(current_dir):
                        all_entries, filtered_entries = reload_dir(parent)
                sel_idx = 0; offset = 0
            elif key.code == term.KEY_ESCAPE:
                search_query = ""; filtered_entries = all_entries; sel_idx = 0; offset = 0
            elif key.lower() == "q" and not search_query:
                break
            elif key.lower() == "s" and not search_query:
                player.stop()
            elif key.lower() == "n" and not search_query:
                files = [t for t in filtered_entries if t.is_file()]
                if files:
                    curr_idx = files.index(player.track) if player.track in files else -1
                    player.play(files[(curr_idx + 1) % len(files)], (curr_idx + 1) % len(files))
            elif key.lower() == "p" and not search_query:
                files = [t for t in filtered_entries if t.is_file()]
                if files:
                    curr_idx = files.index(player.track) if player.track in files else 0
                    player.play(files[(curr_idx - 1) % len(files)], (curr_idx - 1) % len(files))
            elif not key.is_sequence:
                search_query += key
                filtered_entries = [t for t in all_entries if search_query.lower() in t.name.lower()]
                sel_idx = 0; offset = 0

    player.stop()

if __name__ == "__main__":
    main()
