#!/usr/bin/env python3
"""
mplay  ·  terminal music player  (Nerd Font edition)
deps : mpv, blessed
usage: python mplay.py [directory]
"""

import sys, subprocess, threading, time, json, socket, os, shutil, logging, tempfile
from pathlib import Path
from blessed import Terminal
import wcwidth

# ── Logging (silent unless something breaks) ───────────────────────────────────
LOG_DIR = Path.home() / ".cache" / "mplay"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_DIR / "mplay.log"),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
except Exception:
    # if we can't even set up logging, fall back to a null handler rather than crash
    logging.basicConfig(handlers=[logging.NullHandler()])
log = logging.getLogger("mplay")

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
I_VOL    = "\uf028"
I_WARN   = "\uf071"

EXT_ICON = {
    ".mp3": "\uf1c7", ".flac": "\U000f059e", ".ogg": "\U000f0386",
    ".wav": "\U000f033c", ".m4a": "\uf1c7", ".aac": "\uf1c7",
    ".opus": "\U000f0386", ".wma": "\uf1c7", ".ape": "\U000f059e", ".alac": "\U000f059e",
}
AUDIO = set(EXT_ICON.keys())

# ── Helpers ───────────────────────────────────────────────────────────────────
def vwidth(s: str) -> int:
    """Display width of a string in terminal columns — unlike len(), this accounts
    for wide characters (emoji, some CJK) taking 2 columns and combining marks taking 0."""
    total = 0
    for ch in s:
        w = wcwidth.wcwidth(ch)
        total += w if w and w > 0 else 0
    return total

def vtruncate(s: str, max_w: int) -> str:
    """Truncate to a max *display* width, never cutting a wide character in half."""
    out, total = [], 0
    for ch in s:
        w = wcwidth.wcwidth(ch)
        w = w if w and w > 0 else 0
        if total + w > max_w:
            break
        out.append(ch)
        total += w
    return "".join(out)

def vljust(s: str, width: int) -> str:
    """Like str.ljust, but pads based on display width instead of character count."""
    return s + " " * max(0, width - vwidth(s))

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
        log.warning(f"Permission denied scanning {p}")
        return []
    except OSError as e:
        log.warning(f"Error scanning {p}: {e}")
        return []
    return dirs + files

def ipc_socket_path() -> str:
    """Pick a writable tmp dir that works both inside and outside Termux, unique per-process
    so multiple mplay instances don't collide."""
    prefix = os.environ.get("PREFIX")
    tmp_dir = f"{prefix}/tmp" if prefix else tempfile.gettempdir()
    return os.path.join(tmp_dir, f"mplay_{os.getpid()}.sock")

# ── player ────────────────────────────────────────────────────────────────────
class Player:
    def __init__(self):
        self.idx:        int | None = None
        self.track:      Path | None = None
        self.proc:       subprocess.Popen | None = None
        self.elapsed:    float = 0.0
        self.duration:   float = 0.0
        self.paused:     bool = False
        self.volume:     float = 100.0
        self.ipc_path:   str = ipc_socket_path()
        self._tick_stop = threading.Event()
        self.last_error: str | None = None
        self._error_until: float = 0.0

    def _set_error(self, msg: str, ttl: float = 4.0):
        self.last_error = msg
        self._error_until = time.time() + ttl
        log.error(msg)

    def error_active(self) -> bool:
        return bool(self.last_error) and time.time() < self._error_until

    def _get_ipc(self, command):
        if not os.path.exists(self.ipc_path):
            return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                s.connect(self.ipc_path)
                s.sendall((json.dumps({"command": command}) + "\n").encode())
                res = s.recv(1024).decode()
                return json.loads(res.split('\n')[0]).get("data")
        except (OSError, socket.timeout):
            # mpv socket not ready / connection dropped — normal transient state, not fatal
            return None
        except (json.JSONDecodeError, UnicodeDecodeError, IndexError, KeyError) as e:
            log.debug(f"ipc parse issue for {command}: {e}")
            return None

    def toggle_pause(self):
        if self.proc:
            self.paused = not self.paused
            self._get_ipc(["set_property", "pause", self.paused])

    def seek(self, offset: float):
        """Relative seek in seconds (positive = forward, negative = rewind)."""
        if not self.proc:
            return
        self._get_ipc(["seek", offset, "relative"])
        # optimistic local update so the progress bar feels instant; the tick
        # thread will correct it from mpv's real position shortly after
        new_elapsed = self.elapsed + offset
        if self.duration > 0:
            new_elapsed = max(0.0, min(new_elapsed, self.duration))
        else:
            new_elapsed = max(0.0, new_elapsed)
        self.elapsed = new_elapsed

    def volume_up(self, step: float = 5.0):
        self.volume = min(150.0, self.volume + step)
        if self.proc: self._get_ipc(["set_property", "volume", self.volume])

    def volume_down(self, step: float = 5.0):
        self.volume = max(0.0, self.volume - step)
        if self.proc: self._get_ipc(["set_property", "volume", self.volume])

    def play(self, track: Path, idx: int):
        if not shutil.which("mpv"):
            self._set_error(f"{I_WARN} mpv not found — run install.sh", ttl=6.0)
            return
        self._kill()
        self.idx = idx; self.track = track; self.elapsed = 0.0; self.duration = 0.0; self.paused = False
        try:
            os.makedirs(os.path.dirname(self.ipc_path), exist_ok=True)
            self.proc = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet",
                 f"--volume={int(self.volume)}",
                 f"--input-ipc-server={self.ipc_path}", str(track)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._tick_stop.clear()
            threading.Thread(target=self._tick, daemon=True).start()
        except FileNotFoundError:
            self._set_error(f"{I_WARN} mpv not found — run install.sh", ttl=6.0)
            self.idx = None
        except OSError as e:
            self._set_error(f"{I_WARN} couldn't start mpv: {e}", ttl=6.0)
            self.idx = None

    def _tick(self):
        while not self._tick_stop.is_set():
            time.sleep(0.5)
            if self.proc and self.proc.poll() is None:
                curr = self._get_ipc(["get_property", "time-pos"])
                dur = self._get_ipc(["get_property", "duration"])
                try:
                    if curr is not None: self.elapsed = float(curr)
                    if dur is not None: self.duration = float(dur)
                except (TypeError, ValueError):
                    pass

    def _kill(self):
        self._tick_stop.set()
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try: self.proc.kill()
                except OSError as e: log.debug(f"couldn't force-kill mpv: {e}")
            except OSError as e:
                log.debug(f"error terminating mpv: {e}")
            self.proc = None
        if os.path.exists(self.ipc_path):
            try: os.remove(self.ipc_path)
            except OSError as e: log.debug(f"couldn't remove ipc socket: {e}")

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
    out.append(term.move(2, 2) + term.bold_cyan(vtruncate(search_bar, w-4)))

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
            line = vljust(vtruncate(line, w-6), w-4)

            if is_sel:
                out.append(term.move(5 + i, 2) + term.on_blue(term.white(line)))
            elif item.is_dir():
                out.append(term.move(5 + i, 2) + term.yellow(line))
            elif is_playing:
                out.append(term.move(5 + i, 2) + term.blue(line))
            else:
                out.append(term.move(5 + i, 2) + line)

    # Now Playing / error banner
    if player.error_active():
        np_y = h - 4
        out.append(term.move(np_y, 2) + term.bold_red(player.last_error[:w-4]))
    elif player.idx is not None:
        np_y = h - 4
        track, el, dur = player.track, player.elapsed, player.duration
        ratio = (el / dur) if dur > 0 else 0.0
        vol_str = f"  {I_VOL} {int(player.volume):>3}%"
        bar_w = max(10, w - 24 - len(vol_str))
        filled = int(bar_w * ratio)
        status = I_PAUSE if player.paused else I_PLAY
        out.append(term.move(np_y, 2) + term.bold_blue(f"{status} {vtruncate(track.stem, w-10)}"))
        bar = term.blue("█" * filled) + term.gray("░" * (bar_w - filled))
        out.append(term.move(np_y + 1, 2) + f"  {ftime(el)} {bar} {ftime(dur)}{term.cyan(vol_str)}")

    # Dynamic Footer Tutorial
    if player.idx is not None:
        # Player Mode Footer
        help_keys = [
            ("SPC", "Play/Pause", term.magenta),
            ("N/P", "2xTap=Seek", term.blue),
            ("+/-", "Vol", term.green),
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

    sep = "   "
    plain_items = [f"{k} {v}" for k, v, _ in help_keys]
    rendered_items = [f"{term.bold(k)} {col(v)}" for k, v, col in help_keys]
    kept, total = [], 0
    for plain, rendered in zip(plain_items, rendered_items):
        add_len = len(plain) + (len(sep) if kept else 0)
        if total + add_len > w - 2:
            break
        total += add_len
        kept.append(rendered)
    help_line = sep.join(kept)
    out.append(term.move(h-1, 0) + term.center(help_line))

    sys.stdout.write("".join(out))
    sys.stdout.flush()

def main():
    if not shutil.which("mpv"):
        print(f"{I_WARN}  mpv isn't installed or not on PATH.")
        print("Run install.sh first, or: pkg install mpv")
        return

    term = Terminal()
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1]).expanduser().resolve()
        current_dir = str(target_dir) if target_dir.is_dir() else str(Path.home())
    else:
        current_dir = str(Path.home())

    player = Player()
    sel_idx, offset, search_query = 0, 0, ""
    # a single N/P tap is *deferred* briefly so we can tell it apart from a double-tap:
    # if a second matching tap lands within the window, we seek instead of skipping.
    pending = {"key": None, "t": 0.0}
    DOUBLE_TAP_WINDOW = 0.5   # seconds to wait for a possible second tap
    SEEK_FORWARD  = 5.0       # seconds to jump forward on N-N double-tap
    SEEK_REWIND   = 10.0      # seconds to jump back on P-P double-tap

    def reload_dir(new_dir):
        nonlocal current_dir, sel_idx, offset, search_query
        current_dir = str(new_dir)
        entries = scan(current_dir)
        sel_idx, offset, search_query = 0, 0, ""
        return entries, entries

    def fire_pending():
        """Resolve a deferred single N/P tap into the actual track skip."""
        if pending["key"] == "n":
            files = [t for t in filtered_entries if t.is_file()]
            if files:
                curr_idx = files.index(player.track) if player.track in files else -1
                player.play(files[(curr_idx + 1) % len(files)], (curr_idx + 1) % len(files))
        elif pending["key"] == "p":
            files = [t for t in filtered_entries if t.is_file()]
            if files:
                curr_idx = files.index(player.track) if player.track in files else 0
                player.play(files[(curr_idx - 1) % len(files)], (curr_idx - 1) % len(files))
        pending["key"] = None

    all_entries = scan(current_dir)
    filtered_entries = all_entries

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            try:
                # a deferred single N/P tap that never got a follow-up tap resolves here,
                # even if the user hasn't pressed anything else since
                if pending["key"] and (time.time() - pending["t"]) >= DOUBLE_TAP_WINDOW:
                    fire_pending()

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

                if key.lower() not in ("n", "p") and pending["key"]:
                    fire_pending()  # any other key resolves a pending single tap first

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
                    now = time.time()
                    if pending["key"] == "p":
                        fire_pending()  # a stale pending P tap resolves before we start a new one
                    if pending["key"] == "n" and (now - pending["t"]) < DOUBLE_TAP_WINDOW and player.idx is not None:
                        player.seek(SEEK_FORWARD)
                        pending["key"] = None
                    else:
                        pending["key"] = "n"; pending["t"] = now
                elif key.lower() == "p" and not search_query:
                    now = time.time()
                    if pending["key"] == "n":
                        fire_pending()  # a stale pending N tap resolves before we start a new one
                    if pending["key"] == "p" and (now - pending["t"]) < DOUBLE_TAP_WINDOW and player.idx is not None:
                        player.seek(-SEEK_REWIND)
                        pending["key"] = None
                    else:
                        pending["key"] = "p"; pending["t"] = now
                elif key in ("+", "=") and not search_query:
                    player.volume_up()
                elif key in ("-", "_") and not search_query:
                    player.volume_down()
                elif not key.is_sequence:
                    search_query += key
                    filtered_entries = [t for t in all_entries if search_query.lower() in t.name.lower()]
                    sel_idx = 0; offset = 0
            except Exception as e:
                # never let one bad iteration (a resize glitch, an mpv hiccup, etc.)
                # take the whole player down mid-song
                log.exception(f"loop error: {e}")
                continue

    player.stop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("fatal error")
        print(f"mplay crashed — see {LOG_DIR / 'mplay.log'} for details")
