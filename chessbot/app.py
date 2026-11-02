"""The app window: choose a bot, press Play, and it takes over from there."""

import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import chess

from . import bots, capture, game, locate, mouse
from .paths import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"
AUTO_SIDE = "Whichever side is at the bottom"
SIDES = {AUTO_SIDE: None, "White": chess.WHITE, "Black": chess.BLACK}
GAME_FINISHED = object()
POLL_MS = 100
COUNTDOWN_SECONDS = 3
SCREEN_MARGIN = 12
CORNER_NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")
PRIVACY_PAGES = {
    "Screen Recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "Accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
}
PLAY_COLOR = "#2e9e5b"
STOP_COLOR = "#c8443c"


def missing_permissions():
    missing = []
    if not capture.has_screen_recording():
        missing.append("Screen Recording")
    if not mouse.has_accessibility():
        missing.append("Accessibility")
    return missing


class App:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.running = False
        self.corners = []
        self.saved = self._load_settings()

        root.title("Chess Bot")
        root.resizable(False, True)
        root.attributes("-topmost", True)  # stays visible while you click on the board

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        self.status = ttk.Label(frame, text="Open a chess game, then press Play.", wraplength=310)
        self.status.grid(row=0, column=0, sticky="ew")

        self.permission_box = ttk.Frame(frame)
        self.permission_box.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.play_button = tk.Label(frame, text="▶  Play", fg="white", bg=PLAY_COLOR, font=("Helvetica", 18, "bold"), pady=12, cursor="pointinghand")
        self.play_button.grid(row=2, column=0, sticky="ew", pady=12)
        self.play_button.bind("<Button-1>", lambda event: self._toggle())

        self.controls = []
        self._build_bot_row(frame, 3)
        self._build_time_row(frame, 4)
        self._build_side_row(frame, 5)
        self._build_advanced(frame, 6)

        self.log_box = tk.Text(frame, height=6, width=38, state="disabled", wrap="word", font=("Menlo", 12))
        self.log_box.grid(row=7, column=0, sticky="nsew", pady=(10, 0))
        frame.rowconfigure(7, weight=1)

        self._refresh_permissions(request=True)
        self._move_to_right_edge()
        root.protocol("WM_DELETE_WINDOW", self._quit)
        root.after(POLL_MS, self._drain_messages)

    def _move_to_right_edge(self):
        """Start out of the way, since the bot can't see a board this covers."""
        self.root.update_idletasks()
        x = self.root.winfo_screenwidth() - self.root.winfo_reqwidth() - SCREEN_MARGIN
        self.root.geometry(f"+{x}+{SCREEN_MARGIN * 4}")

    def _build_bot_row(self, parent, row):
        box = ttk.LabelFrame(parent, text="Bot", padding=6)
        box.grid(row=row, column=0, sticky="ew")
        box.columnconfigure(0, weight=1)
        self.bot_choice = ttk.Combobox(box, state="readonly")
        self.bot_choice.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.bot_choice.bind("<<ComboboxSelected>>", lambda event: self._update_remove_button())
        add = ttk.Button(box, text="Add Bot…", command=self._add_bot)
        add.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.remove_button = ttk.Button(box, text="Remove", command=self._remove_bot)
        self.remove_button.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.controls += [self.bot_choice, add]
        self._reload_bots(self.saved.get("bot"))

    def _build_time_row(self, parent, row):
        box = ttk.Frame(parent)
        box.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        box.columnconfigure(0, weight=1)
        self.movetime = tk.DoubleVar(value=self.saved.get("movetime", 2.0))
        self.time_label = ttk.Label(box)
        self.time_label.grid(row=0, column=0, sticky="w")
        scale = ttk.Scale(box, from_=0.5, to=10, variable=self.movetime, command=lambda value: self._show_time())
        scale.grid(row=1, column=0, sticky="ew")
        self.controls.append(scale)
        self._show_time()

    def _build_side_row(self, parent, row):
        box = ttk.Frame(parent)
        box.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Bot plays:").grid(row=0, column=0, padx=(0, 6))
        self.side_choice = ttk.Combobox(box, state="readonly", values=list(SIDES))
        self.side_choice.set(self.saved.get("side", AUTO_SIDE))
        self.side_choice.grid(row=0, column=1, sticky="ew")
        self.controls.append(self.side_choice)

    def _build_advanced(self, parent, row):
        box = ttk.LabelFrame(parent, text="If the bot can't start", padding=6)
        box.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        box.columnconfigure(0, weight=1)
        ttk.Label(box, text="Game already started? Paste its position (FEN) and pick a side:", wraplength=300).grid(row=0, column=0, sticky="w")
        self.fen = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.fen)
        entry.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        self.corners_button = ttk.Button(box, text="Show Me Where the Board Is", command=self._start_pointing)
        self.corners_button.grid(row=2, column=0, sticky="ew")
        self.controls += [entry, self.corners_button]

    def _load_settings(self):
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text())
        return {}

    def _save_settings(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(
                {
                    "bot": self.bot_choice.get(),
                    "movetime": round(self.movetime.get(), 1),
                    "side": self.side_choice.get(),
                }
            )
        )

    def _show_time(self):
        self.time_label.config(text=f"Time per move: {self.movetime.get():.1f} s")

    def _reload_bots(self, selected=None):
        self.bots = {bot.name: bot for bot in bots.installed_bots()}
        self.bot_choice.config(values=list(self.bots))
        if selected not in self.bots:
            selected = bots.BUILT_IN_BOT.name
        self.bot_choice.set(selected)
        self._update_remove_button()

    def _update_remove_button(self):
        built_in = self.bots[self.bot_choice.get()].kind == bots.BUILT_IN
        self.remove_button.state(["disabled" if built_in else "!disabled"])

    def _add_bot(self):
        self.root.attributes("-topmost", False)
        try:
            accepted = messagebox.askokcancel(
                "Add a bot",
                "A bot is a program that will run on your Mac, so only add ones you trust.\n\n"
                "Pick a UCI chess engine (such as Stockfish) or a Python file with a "
                "choose_move function.",
            )
            path = filedialog.askopenfilename(title="Choose a bot") if accepted else ""
            if not path:
                return
            try:
                bot = bots.install(path)
            except bots.BotError as error:
                messagebox.showerror("That bot didn't work", str(error))
                return
            self._reload_bots(bot.name)
            self._say(f"Added {bot.name}.")
        finally:
            self.root.attributes("-topmost", True)

    def _remove_bot(self):
        bots.remove(self.bots[self.bot_choice.get()])
        self._reload_bots()

    def _refresh_permissions(self, request=False):
        for child in self.permission_box.winfo_children():
            child.destroy()
        missing = missing_permissions()
        if not missing:
            return True
        if request:
            if "Screen Recording" in missing:
                capture.request_screen_recording()
            if "Accessibility" in missing:
                mouse.request_accessibility()
        ttk.Label(
            self.permission_box,
            text="Chess Bot needs your OK before it can see the board and move the mouse. "
            "Turn it on in each list below, then quit and reopen Chess Bot.",
            wraplength=310,
        ).pack(fill="x")
        for name in missing:
            ttk.Button(
                self.permission_box,
                text=f"Open {name} Settings",
                command=lambda page=PRIVACY_PAGES[name]: subprocess.run(["open", page], check=False),
            ).pack(fill="x", pady=(4, 0))
        return False

    def _toggle(self):
        if self.running:
            mouse.press_stop()
            self.status.config(text="Stopping...")
        else:
            self._play()

    def _read_settings(self):
        """The choices on screen as game settings, or None if they don't work."""
        settings = game.Settings(
            bot=self.bots[self.bot_choice.get()],
            movetime=self.movetime.get(),
            side=SIDES[self.side_choice.get()],
            fen=self.fen.get().strip(),
        )
        if settings.fen:
            try:
                chess.Board(settings.fen)
            except ValueError:
                self.status.config(text="That position isn't valid FEN.")
                return None
            if settings.side is None:
                self.status.config(text="To join a game already started, choose White or Black.")
                return None
        return settings

    def _play(self):
        if not self._refresh_permissions():
            return
        settings = self._read_settings()
        if settings is None:
            return
        self._save_settings()
        self.running = True
        mouse.clear_stop()
        self.play_button.config(text="■  Stop", bg=STOP_COLOR)
        for control in self.controls:
            control.state(["disabled"])
        threading.Thread(target=self._run_game, args=(settings,), daemon=True).start()

    def _run_game(self, settings):
        try:
            game.play(settings, log=self.messages.put)
        except mouse.StopRequested:
            self.messages.put("Stopped.")
        except bots.BotError as error:
            self.messages.put(str(error))
        except Exception as error:
            self.messages.put(f"Something went wrong: {error}")
        finally:
            self.messages.put(GAME_FINISHED)

    def _say(self, message):
        self.status.config(text=message)
        self.log_box.config(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _drain_messages(self):
        while not self.messages.empty():
            message = self.messages.get()
            if message is GAME_FINISHED:
                self._game_finished()
            else:
                self._say(message)
        self.root.after(POLL_MS, self._drain_messages)

    def _game_finished(self):
        self.running = False
        self.play_button.config(text="▶  Play", bg=PLAY_COLOR)
        for control in self.controls:
            control.state(["!disabled"])
        if self.side_choice.get() in SIDES:
            self.side_choice.state(["readonly"])
        self.bot_choice.state(["readonly"])

    def _start_pointing(self):
        self.corners = []
        self._count_down(COUNTDOWN_SECONDS)

    def _count_down(self, seconds):
        name = CORNER_NAMES[len(self.corners)]
        if seconds > 0:
            self.status.config(text=f"Hold the mouse over the {name} corner of the 64 squares... {seconds}")
            self.root.after(1000, self._count_down, seconds - 1)
            return
        self.corners.append(mouse.position())
        if len(self.corners) < len(CORNER_NAMES):
            self._count_down(COUNTDOWN_SECONDS)
        else:
            locate.save_corners(self.corners)
            self.status.config(text="Got it. Press Play.")

    def _quit(self):
        mouse.press_stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
