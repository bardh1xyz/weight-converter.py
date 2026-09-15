# Weight Converter - kg <-> lbs, with history and light/dark themes.

import json
import math
import platform
import re
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont

APP_VERSION = "3.0"
APP_DIR = Path.home() / ".weight_converter"
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"
MAX_HISTORY = 12
PLACEHOLDER = "Your result will show up here"

KG_PER_LB = 0.45359237
LB_PER_KG = 1 / KG_PER_LB

TWITTER_URL = "https://x.com/bardhzzYFN"
GITHUB_URL = "https://github.com/bardh1xyz"

MSG_ENTER_WEIGHT = "Enter a weight to convert."
MSG_INVALID_NUMBER = "That doesn't look like a number."
MSG_TOO_SMALL = "Weight has to be more than zero."
MSG_TOO_BIG = "That number's too large to convert."
MSG_COPIED = "\u2713 Copied"

LIGHT = {
    "bg": "#FAFAFB",
    "card": "#FFFFFF",
    "input": "#F5F5F7",
    "text": "#18181B",
    "muted": "#71717A",
    "faint": "#A1A1AA",
    "border": "#E4E4E7",
    "focus": "#A5B4FC",
    "accent": "#4F46E5",
    "accent_hover": "#4338CA",
    "accent_soft": "#EEF2FF",
    "accent_border": "#C7D2FE",
    "red": "#DC2626",
    "green": "#16A34A",
    "history_bg": "#FCFCFD",
    "selected": "#E0E7FF",
    "selected_text": "#4338CA",
}

DARK = {
    "bg": "#0A0A0B",
    "card": "#141416",
    "input": "#1C1C1F",
    "text": "#F4F4F5",
    "muted": "#A1A1AA",
    "faint": "#52525B",
    "border": "#27272A",
    "focus": "#6366F1",
    "accent": "#6366F1",
    "accent_hover": "#818CF8",
    "accent_soft": "#1C1A2E",
    "accent_border": "#312E63",
    "red": "#F87171",
    "green": "#4ADE80",
    "history_bg": "#101012",
    "selected": "#242043",
    "selected_text": "#C7D2FE",
}


def pick_ui_font(root):
    # "Segoe UI" only exists on Windows, so on Mac/Linux the app would've
    # silently fallen back to whatever Tk feels like. Pick something decent
    # that's actually installed instead.
    wanted = ["SF Pro Text", "Segoe UI", "Helvetica Neue", "Ubuntu", "Noto Sans", "Helvetica", "Arial"]
    installed = set(tkfont.families(root))
    for name in wanted:
        if name in installed:
            return name
    return "TkDefaultFont"


def detect_windows_dark_mode():
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except OSError:
        return False


def parse_weight(raw):
    """'70', '1,234.5', '+3.2' -> float. Anything else -> None."""
    text = raw.strip().replace(" ", "")
    if not text:
        return None

    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]

    if not text or not re.fullmatch(r"[0-9][0-9,.]*", text):
        return None

    # comma = thousands separator, dot = decimal point - matches how
    # format_number() below writes numbers back out
    text = text.replace(",", "")
    if text.count(".") > 1:
        return None

    try:
        value = float(sign + text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def format_number(value):
    value = float(value)
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


class WeightConverterApp:
    def __init__(self, root):
        self.root = root
        self.settings = {
            "theme": "system",
            "remember_window": True,
            "remember_unit": True,
            "remember_history": True,
        }
        self.theme = "system"
        self.dark = False
        self.colors = LIGHT
        self.ui_font = "TkDefaultFont"

        self.unit_var = tk.StringVar(master=root, value="kg")
        self.weight_var = tk.StringVar(master=root)

        self.result_text = ""     # full line, e.g. "70 kg  =  154.32 lbs"
        self.result_value = ""    # just "154.32 lbs"
        self.has_result = False
        self.status_kind = "muted"
        self.history = []

        self.about_win = None
        self.settings_win = None
        self.toast = None
        self.theme_poll_job = None
        self.debounce_job = None
        self.copy_flash_job = None
        self.fullscreen = False
        self.suppress_trace = False
        self.theme_before_preview = None

        self.load_settings()
        self.build_window()
        self.build_menu()
        self.build_layout()
        self.finalize_window_size()
        self.bind_shortcuts()
        self.load_history()

        self.set_theme(self.theme, persist=False, announce=None)
        self.refresh_history()
        self.entry.focus_set()

    # ---- settings / history on disk -----------------------------------

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            for key in self.settings:
                if key in data:
                    self.settings[key] = data[key]

        theme = self.settings.get("theme", "system")
        self.theme = theme if theme in ("system", "light", "dark") else "system"

        if self.settings.get("remember_unit", True):
            unit = self.settings.get("last_unit", "kg")
            if unit in ("kg", "lbs"):
                self.unit_var.set(unit)

    def save_settings(self):
        self.settings["theme"] = self.theme
        self.settings["last_unit"] = self.unit_var.get()
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    def load_history(self):
        if not self.settings.get("remember_history", True):
            return
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.history = []
            return
        if not isinstance(data, list):
            self.history = []
            return
        needed = ("time", "text", "value", "unit", "target", "converted")
        self.history = [
            item for item in data[:MAX_HISTORY]
            if isinstance(item, dict) and all(k in item for k in needed) and item.get("unit") in ("kg", "lbs")
        ]

    def save_history(self):
        if not self.settings.get("remember_history", True):
            return
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.history[:MAX_HISTORY], indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---- window setup ---------------------------------------------------

    def build_window(self):
        self.root.title("Weight Converter")
        self.ui_font = pick_ui_font(self.root)
        self.root.configure(bg=self.colors["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def finalize_window_size(self):
        # The old fixed minsize was smaller than the content actually needed,
        # which is why the copy button used to get cut off. Measure the real
        # layout instead of guessing a number.
        self.root.update_idletasks()
        min_w = max(760, self.root.winfo_reqwidth() + 16)
        min_h = max(640, self.root.winfo_reqheight() + 16)
        self.root.minsize(min_w, min_h)

        geometry = self.settings.get("geometry")
        if (
            self.settings.get("remember_window", True)
            and isinstance(geometry, str)
            and self.geometry_fits(geometry, min_w, min_h)
        ):
            try:
                self.root.geometry(geometry)
                return
            except tk.TclError:
                pass
        self.center_window(self.root, max(min_w, 900), max(min_h, 720))

    @staticmethod
    def geometry_fits(geometry, min_w, min_h):
        match = re.match(r"(\d+)x(\d+)", geometry)
        if not match:
            return False
        width, height = int(match.group(1)), int(match.group(2))
        return width >= min_w and height >= min_h

    @staticmethod
    def center_window(window, width, height):
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def build_menu(self):
        menubar = tk.Menu(self.root, tearoff=False)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Clear Input", accelerator="Esc", command=self.clear_input)
        file_menu.add_command(label="Clear History", accelerator="Ctrl+Shift+L", command=self.clear_history)
        file_menu.add_separator()
        file_menu.add_command(label="Copy Result", accelerator="Ctrl+C", command=self.copy_result)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Ctrl+Q", command=self.on_close)

        self.view_menu = tk.Menu(menubar, tearoff=False)
        for mode in ("light", "dark", "system"):
            self.view_menu.add_command(label=mode.title(), command=lambda m=mode: self.set_theme(m))
        self.view_menu.add_separator()
        self.view_menu.add_command(label="Toggle Fullscreen", accelerator="F11", command=self.toggle_fullscreen)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="Swap Units", accelerator="Ctrl+Shift+S", command=self.swap_units)
        tools_menu.add_command(label="Settings", command=self.open_settings)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="GitHub", command=lambda: self.open_link(GITHUB_URL))
        help_menu.add_command(label="X / Twitter", command=lambda: self.open_link(TWITTER_URL))

        menubar.add_cascade(label="File", menu=file_menu)
        menubar.add_cascade(label="View", menu=self.view_menu)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)
        self.refresh_view_menu()

    def refresh_view_menu(self):
        for index, mode in enumerate(("light", "dark", "system")):
            label = f"\u2713  {mode.title()}" if self.theme == mode else mode.title()
            self.view_menu.entryconfigure(index, label=label)

    # ---- layout -----------------------------------------------------------

    def build_layout(self):
        root = self.root
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(root, bd=0)
        self.header.grid(row=0, column=0, sticky="we", padx=32, pady=(24, 16))
        self.title_label = tk.Label(self.header, text="Weight Converter", font=(self.ui_font, 25, "bold"), anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(
            self.header, text="Kilograms and pounds, converted instantly.", font=(self.ui_font, 10), anchor="w"
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        self.body = tk.Frame(root, bd=0)
        self.body.grid(row=1, column=0, sticky="nsew", padx=32)
        self.body.grid_columnconfigure(0, weight=1, uniform="cols")
        self.body.grid_columnconfigure(1, weight=1, uniform="cols")
        self.body.grid_rowconfigure(0, weight=1)

        self.left = tk.Frame(self.body, bd=0)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left.grid_columnconfigure(0, weight=1)
        self.left.grid_rowconfigure(1, weight=1)

        self.right = tk.Frame(self.body, bd=0)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=1)

        self.build_converter_card()
        self.build_result_card()
        self.build_history_card()

        self.statusbar = tk.Frame(root, bd=0)
        self.statusbar.grid(row=2, column=0, sticky="we", padx=32, pady=(16, 20))
        self.status_dot = tk.Label(self.statusbar, text="\u25cf", font=(self.ui_font, 8))
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self.status_label = tk.Label(self.statusbar, text="Ready", font=(self.ui_font, 9), anchor="w")
        self.status_label.pack(side=tk.LEFT)
        self.credit_label = tk.Label(
            self.statusbar, text=f"Made by @bardhzzY  \u2022  v{APP_VERSION}", font=(self.ui_font, 8), cursor="hand2"
        )
        self.credit_label.pack(side=tk.RIGHT)
        self.credit_label.bind("<Button-1>", lambda e: self.open_link(TWITTER_URL))

    def build_converter_card(self):
        self.converter_card = tk.Frame(self.left, bd=0, highlightthickness=1)
        self.converter_card.grid(row=0, column=0, sticky="we")
        self.converter_inner = tk.Frame(self.converter_card, bd=0)
        self.converter_inner.pack(fill=tk.X, padx=24, pady=24)
        inner = self.converter_inner

        self.from_title = tk.Label(inner, text="CONVERT FROM", font=(self.ui_font, 9, "bold"), anchor="w")
        self.from_title.pack(fill=tk.X, pady=(0, 8))

        self.unit_switch = tk.Frame(inner, bd=0, highlightthickness=1)
        self.unit_switch.pack(fill=tk.X, pady=(0, 18))
        self.kg_btn = tk.Button(
            self.unit_switch, text="Kilograms\nkg", command=lambda: self.set_unit("kg"),
            font=(self.ui_font, 10, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", pady=9,
        )
        self.kg_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.lb_btn = tk.Button(
            self.unit_switch, text="Pounds\nlbs", command=lambda: self.set_unit("lbs"),
            font=(self.ui_font, 10, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", pady=9,
        )
        self.lb_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.weight_title = tk.Label(inner, text="WEIGHT", font=(self.ui_font, 9, "bold"), anchor="w")
        self.weight_title.pack(fill=tk.X, pady=(0, 8))

        self.input_box = tk.Frame(inner, bd=0, highlightthickness=1)
        self.input_box.pack(fill=tk.X, pady=(0, 18))
        self.entry = tk.Entry(self.input_box, textvariable=self.weight_var, font=(self.ui_font, 14), relief=tk.FLAT, bd=0)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(14, 6), pady=13)
        self.unit_suffix = tk.Label(self.input_box, text="kg", font=(self.ui_font, 10, "bold"))
        self.unit_suffix.pack(side=tk.RIGHT, padx=14)

        self.convert_btn = tk.Button(
            inner, text="Convert  \u2192", command=self.convert,
            font=(self.ui_font, 11, "bold"), fg="white", relief=tk.FLAT, bd=0, cursor="hand2", pady=12,
        )
        self.convert_btn.pack(fill=tk.X, pady=(0, 8))
        self.swap_btn = tk.Button(
            inner, text="\u21c4  Swap units", command=self.swap_units,
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", pady=8,
        )
        self.swap_btn.pack(fill=tk.X, pady=(0, 2))
        self.clear_btn = tk.Button(
            inner, text="Clear input", command=self.clear_input,
            font=(self.ui_font, 9), relief=tk.FLAT, bd=0, cursor="hand2", pady=8,
        )
        self.clear_btn.pack(fill=tk.X)

    def build_result_card(self):
        # rows 0/1/3 keep their natural height, row 2 is the only one that
        # stretches - so the copy button (row 3) never gets squeezed out.
        card = self.result_card = tk.Frame(self.left, bd=0, highlightthickness=1)
        card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        self.result_title = tk.Label(card, text="RESULT", font=(self.ui_font, 9, "bold"), anchor="w")
        self.result_title.grid(row=0, column=0, sticky="we", padx=20, pady=(16, 2))

        self.result_hint = tk.Label(card, text="Click the value to copy", font=(self.ui_font, 8), anchor="w")
        self.result_hint.grid(row=1, column=0, sticky="we", padx=20)

        self.result_label = tk.Label(
            card, text=PLACEHOLDER, font=(self.ui_font, 18, "bold"),
            anchor="center", justify=tk.CENTER, wraplength=320, cursor="hand2",
        )
        self.result_label.grid(row=2, column=0, sticky="nsew", padx=20, pady=6)
        self.result_label.bind("<Button-1>", lambda e: self.copy_value())
        self.result_label.bind("<Enter>", lambda e: self.on_result_hover(True))
        self.result_label.bind("<Leave>", lambda e: self.on_result_hover(False))

        self.copy_btn = tk.Button(
            card, text="Copy full result", command=self.copy_result,
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=14, pady=8,
        )
        self.copy_btn.grid(row=3, column=0, sticky="e", padx=20, pady=(0, 16))

    def build_history_card(self):
        self.history_head = tk.Frame(self.right, bd=0)
        self.history_head.grid(row=0, column=0, sticky="we", pady=(0, 8))
        self.history_title = tk.Label(self.history_head, text="RECENT CONVERSIONS", font=(self.ui_font, 9, "bold"), anchor="w")
        self.history_title.pack(side=tk.LEFT)
        self.history_count = tk.Label(self.history_head, text="0", font=(self.ui_font, 8, "bold"), anchor="e")
        self.history_count.pack(side=tk.RIGHT)

        self.history_box = tk.Frame(self.right, bd=0, highlightthickness=1)
        self.history_box.grid(row=1, column=0, sticky="nsew")
        self.history_box.grid_columnconfigure(0, weight=1)
        self.history_box.grid_rowconfigure(0, weight=1)

        self.history_list = tk.Listbox(
            self.history_box, font=(self.ui_font, 9), relief=tk.FLAT, bd=0,
            highlightthickness=0, selectborderwidth=0, activestyle="none",
            selectmode=tk.SINGLE, takefocus=0,
        )
        self.history_list.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        self.history_scroll = tk.Scrollbar(
            self.history_box, orient=tk.VERTICAL, command=self.history_list.yview,
            relief=tk.FLAT, bd=0, highlightthickness=0, width=10,
        )
        self.history_scroll.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 6))
        self.history_list.configure(yscrollcommand=self.history_scroll.set)

        self.history_list.bind("<Button-1>", self.on_history_click)
        self.history_list.bind("<Double-Button-1>", self.copy_history_item)
        self.history_list.bind("<Return>", self.copy_history_item)

        self.history_actions = tk.Frame(self.right, bd=0)
        self.history_actions.grid(row=2, column=0, sticky="we", pady=(8, 0))
        self.clear_history_btn = tk.Button(
            self.history_actions, text="Clear history", command=self.clear_history,
            font=(self.ui_font, 8, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=10, pady=7,
        )
        self.clear_history_btn.pack(side=tk.RIGHT)
        self.history_note = tk.Label(
            self.history_actions, text="Double-click to copy \u2022 Click to reuse", font=(self.ui_font, 8), anchor="w"
        )
        self.history_note.pack(side=tk.LEFT)

    # ---- events -------------------------------------------------------

    def bind_shortcuts(self):
        root = self.root
        root.bind("<Return>", lambda e: self.convert())
        root.bind("<Escape>", lambda e: self.clear_input())
        root.bind("<Control-l>", lambda e: self.clear_input())
        root.bind("<Control-L>", lambda e: self.clear_input())
        root.bind("<Control-c>", lambda e: self.copy_result())
        root.bind("<Control-C>", lambda e: self.copy_result())
        root.bind("<Control-Shift-C>", lambda e: self.copy_value())
        root.bind("<Control-Shift-L>", lambda e: self.clear_history())
        root.bind("<Control-Shift-S>", lambda e: self.swap_units())
        root.bind("<Control-q>", lambda e: self.on_close())
        root.bind("<Control-Q>", lambda e: self.on_close())
        root.bind("<F11>", lambda e: self.toggle_fullscreen())
        root.bind("<Configure>", self.on_resize, add="+")

        self.weight_var.trace_add("write", self.on_weight_typed)
        self.entry.bind("<FocusIn>", lambda e: self.on_entry_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self.on_entry_focus(False))

        self.convert_btn.bind("<Enter>", lambda e: self.on_convert_hover(True))
        self.convert_btn.bind("<Leave>", lambda e: self.on_convert_hover(False))
        for btn in (self.kg_btn, self.lb_btn):
            btn.bind("<Enter>", self.on_unit_hover)
            btn.bind("<Leave>", lambda e: self.refresh_unit_buttons())
        self.swap_btn.bind("<Enter>", lambda e: self.on_swap_hover(True))
        self.swap_btn.bind("<Leave>", lambda e: self.on_swap_hover(False))
        self.clear_history_btn.bind("<Enter>", lambda e: self.on_clear_history_hover(True))
        self.clear_history_btn.bind("<Leave>", lambda e: self.on_clear_history_hover(False))

    def on_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        wrap = max(200, self.result_card.winfo_width() - 40)
        self.result_label.configure(wraplength=wrap)
        if self.toast and self.toast.winfo_exists():
            self.place_toast()

    # ---- theme ----------------------------------------------------------

    def set_theme(self, mode, persist=True, announce="Theme updated."):
        if mode not in ("system", "light", "dark"):
            return
        self.theme = mode
        self.dark = detect_windows_dark_mode() if mode == "system" else mode == "dark"
        self.colors = DARK if self.dark else LIGHT
        if persist:
            self.save_settings()
        self.apply_theme()

        # only bother polling for OS theme changes when it's actually possible
        if mode == "system" and platform.system() == "Windows" and not self.theme_poll_job:
            self.poll_system_theme()

        if self.about_win and self.about_win.winfo_exists():
            self.theme_about_window()
        if self.settings_win and self.settings_win.winfo_exists():
            self.theme_settings_window()
        if announce:
            self.set_status(announce, "success")

    def poll_system_theme(self):
        if not self.root.winfo_exists() or self.theme != "system":
            self.theme_poll_job = None
            return
        is_dark = detect_windows_dark_mode()
        if is_dark != self.dark:
            self.dark = is_dark
            self.colors = DARK if is_dark else LIGHT
            self.apply_theme()
        self.theme_poll_job = self.root.after(5000, self.poll_system_theme)

    def apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])

        for widget in (self.header, self.body, self.left, self.right, self.statusbar, self.history_head, self.history_actions):
            widget.configure(bg=c["bg"])

        self.title_label.configure(bg=c["bg"], fg=c["text"])
        self.subtitle_label.configure(bg=c["bg"], fg=c["muted"])
        self.status_dot.configure(bg=c["bg"])
        self.status_label.configure(bg=c["bg"])
        self.credit_label.configure(bg=c["bg"], fg=c["faint"])

        self.converter_card.configure(bg=c["card"], highlightbackground=c["border"], highlightcolor=c["border"])
        self.converter_inner.configure(bg=c["card"])
        self.from_title.configure(bg=c["card"], fg=c["muted"])
        self.weight_title.configure(bg=c["card"], fg=c["muted"])
        self.unit_switch.configure(bg=c["input"], highlightbackground=c["border"], highlightcolor=c["border"])
        self.input_box.configure(bg=c["input"], highlightbackground=c["border"], highlightcolor=c["border"])
        self.entry.configure(
            bg=c["input"], fg=c["text"], insertbackground=c["text"],
            selectbackground=c["accent"], selectforeground="white",
        )
        self.unit_suffix.configure(bg=c["input"], fg=c["muted"])
        self.convert_btn.configure(bg=c["accent"], activebackground=c["accent_hover"], activeforeground="white")
        self.swap_btn.configure(bg=c["card"], fg=c["muted"], activebackground=c["border"], activeforeground=c["text"])
        self.clear_btn.configure(bg=c["card"], fg=c["muted"], activebackground=c["border"], activeforeground=c["text"])

        self.result_card.configure(bg=c["accent_soft"], highlightbackground=c["accent_border"], highlightcolor=c["accent_border"])
        self.result_title.configure(bg=c["accent_soft"], fg=c["muted"])
        self.result_hint.configure(bg=c["accent_soft"], fg=c["muted"])
        self.style_result_text()
        self.copy_btn.configure(bg=c["accent_soft"], fg=c["accent"], activebackground=c["accent_soft"], activeforeground=c["accent_hover"])

        self.history_box.configure(bg=c["history_bg"], highlightbackground=c["border"], highlightcolor=c["border"])
        self.history_list.configure(
            bg=c["history_bg"], fg=c["text"], selectbackground=c["selected"],
            selectforeground=c["selected_text"], highlightthickness=0,
        )
        self.history_scroll.configure(bg=c["border"], troughcolor=c["history_bg"], activebackground=c["faint"])
        self.history_title.configure(bg=c["bg"], fg=c["muted"])
        self.history_count.configure(bg=c["bg"], fg=c["faint"])
        self.clear_history_btn.configure(bg=c["bg"], fg=c["muted"], activebackground=c["border"], activeforeground=c["text"])
        self.history_note.configure(bg=c["bg"], fg=c["faint"])

        self.refresh_unit_buttons()
        self.refresh_view_menu()
        self.refresh_history()
        self.set_status(self.status_label.cget("text"), self.status_kind)

        if self.toast and self.toast.winfo_exists():
            self.toast.configure(bg=c["card"])
            self.place_toast()

    def style_result_text(self):
        c = self.colors
        current = self.result_label.cget("text")
        if current == PLACEHOLDER:
            fg = c["muted"]
        elif current in (MSG_ENTER_WEIGHT, MSG_INVALID_NUMBER, MSG_TOO_SMALL, MSG_TOO_BIG):
            fg = c["red"]
        elif current == MSG_COPIED:
            fg = c["green"]
        else:
            fg = c["accent"]
        self.result_label.configure(bg=c["accent_soft"], fg=fg)

    def refresh_unit_buttons(self):
        current = self.unit_var.get()
        self.style_toggle_button(self.kg_btn, current == "kg")
        self.style_toggle_button(self.lb_btn, current == "lbs")
        self.unit_suffix.configure(text=current)

    def style_toggle_button(self, button, selected):
        c = self.colors
        bg = c["selected"] if selected else c["input"]
        fg = c["selected_text"] if selected else c["muted"]
        button.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)

    # ---- hover states ---------------------------------------------------

    def on_entry_focus(self, focused):
        color = self.colors["focus"] if focused else self.colors["border"]
        self.input_box.configure(highlightbackground=color, highlightcolor=color)

    def on_convert_hover(self, on):
        self.convert_btn.configure(bg=self.colors["accent_hover"] if on else self.colors["accent"])

    def on_unit_hover(self, event):
        button = event.widget
        selected_btn = self.kg_btn if self.unit_var.get() == "kg" else self.lb_btn
        if button is not selected_btn:
            button.configure(bg=self.colors["accent_soft"], fg=self.colors["text"])

    def on_swap_hover(self, on):
        c = self.colors
        if on:
            self.swap_btn.configure(bg=c["accent_soft"], fg=c["accent"])
        else:
            self.swap_btn.configure(bg=c["card"], fg=c["muted"])

    def on_clear_history_hover(self, on):
        self.clear_history_btn.configure(bg=self.colors["border"] if on else self.colors["bg"])

    def on_result_hover(self, on):
        if not self.has_result:
            return
        self.result_label.configure(fg=self.colors["accent_hover"] if on else self.colors["accent"])

    # ---- conversion -----------------------------------------------------

    def on_weight_typed(self, *_args):
        if self.suppress_trace:
            return
        if self.debounce_job:
            self.root.after_cancel(self.debounce_job)
            self.debounce_job = None
        if not self.weight_var.get().strip():
            self.reset_result()
            self.set_status("Ready", "muted")
            return
        self.debounce_job = self.root.after(180, self.live_convert)

    def live_convert(self):
        self.debounce_job = None
        self.convert(record=False, quiet=True)

    def set_unit(self, unit):
        if unit not in ("kg", "lbs"):
            return
        self.unit_var.set(unit)
        self.refresh_unit_buttons()
        if self.weight_var.get().strip():
            self.convert(record=False, quiet=True)
        self.save_settings()

    def swap_units(self):
        if self.has_result and self.result_value:
            self.suppress_trace = True
            try:
                self.unit_var.set(self.result_value.split()[-1])
                self.weight_var.set(format_number(self.result_number()))
            finally:
                self.suppress_trace = False
            self.refresh_unit_buttons()
            self.convert()
            return

        self.unit_var.set("lbs" if self.unit_var.get() == "kg" else "kg")
        self.refresh_unit_buttons()
        if self.weight_var.get().strip():
            self.convert(record=False, quiet=True)
        self.save_settings()
        self.set_status("Input unit changed.", "success")

    def result_number(self):
        if not self.result_value:
            return 0.0
        return parse_weight(self.result_value.split()[0]) or 0.0

    def convert(self, record=True, quiet=False):
        raw = self.weight_var.get().strip()
        if not raw:
            if not quiet:
                self.show_error(MSG_ENTER_WEIGHT)
            return False

        number = parse_weight(raw)
        if number is None:
            if not quiet or self.has_result:
                self.show_error(MSG_INVALID_NUMBER)
            return False
        if number <= 0:
            if not quiet or self.has_result:
                self.show_error(MSG_TOO_SMALL)
            return False
        if number > 1e15:
            if not quiet or self.has_result:
                self.show_error(MSG_TOO_BIG)
            return False

        unit = self.unit_var.get()
        if unit == "kg":
            converted = number * LB_PER_KG
            target = "lbs"
        else:
            converted = number * KG_PER_LB
            target = "kg"

        source_text = format_number(number)
        converted_text = format_number(converted)
        self.result_text = f"{source_text} {unit}  =  {converted_text} {target}"
        self.result_value = f"{converted_text} {target}"
        self.has_result = True
        self.result_label.configure(text=self.result_value)
        self.result_hint.configure(text="Click the value to copy")
        self.style_result_text()
        self.set_status("Conversion updated." if quiet else "Conversion completed.", "success")

        if record:
            self.remember_conversion(self.result_text, number, unit, target, converted)
        return True

    def show_error(self, message):
        self.result_text = ""
        self.result_value = ""
        self.has_result = False
        self.result_label.configure(text=message)
        self.result_hint.configure(text="Enter a valid number")
        self.style_result_text()
        self.set_status("Please fix the input above.", "danger")

    def reset_result(self):
        self.result_text = ""
        self.result_value = ""
        self.has_result = False
        self.result_label.configure(text=PLACEHOLDER)
        self.result_hint.configure(text="Click the value to copy")
        self.style_result_text()

    # ---- history ----------------------------------------------------------

    def remember_conversion(self, text, number, unit, target, converted):
        self.history = [item for item in self.history if item.get("text") != text]
        self.history.insert(0, {
            "time": datetime.now().strftime("%H:%M"),
            "text": text,
            "value": float(number),
            "unit": unit,
            "target": target,
            "converted": float(converted),
        })
        self.history = self.history[:MAX_HISTORY]
        self.save_history()
        self.refresh_history()

    def refresh_history(self):
        if not hasattr(self, "history_list"):
            return
        self.history_list.delete(0, tk.END)
        if self.history:
            for item in self.history:
                self.history_list.insert(tk.END, f"{item['time']}   \u2022   {item['text']}")
            self.history_list.configure(fg=self.colors["text"])
        else:
            self.history_list.insert(tk.END, "Nothing here yet - conversions you run will show up in this list.")
            self.history_list.configure(fg=self.colors["faint"])
        self.history_count.configure(text=str(len(self.history)))

    def on_history_click(self, event):
        if not self.history:
            return
        index = self.history_list.nearest(event.y)
        if not 0 <= index < len(self.history):
            return
        item = self.history[index]
        self.suppress_trace = True
        try:
            self.unit_var.set(item["unit"])
            self.weight_var.set(format_number(item["value"]))
        finally:
            self.suppress_trace = False
        self.refresh_unit_buttons()
        self.convert(record=False, quiet=True)
        self.set_status("History entry loaded.", "success")

    def copy_history_item(self, _event=None):
        if not self.history:
            return "break"
        selection = self.history_list.curselection()
        if not selection or selection[0] >= len(self.history):
            return "break"
        self.copy_text(self.history[selection[0]]["text"], "History entry copied.")
        return "break"

    def clear_history(self):
        if not self.history:
            self.set_status("History is already empty.", "muted")
            return
        if not self.ask_confirm("Clear history", "This removes all saved conversions. Continue?"):
            return
        self.history.clear()
        try:
            HISTORY_FILE.unlink(missing_ok=True)
        except OSError:
            self.save_history()
        self.refresh_history()
        self.set_status("History cleared.", "success")

    # ---- input / clipboard / toast ---------------------------------------

    def clear_input(self):
        self.suppress_trace = True
        try:
            self.weight_var.set("")
        finally:
            self.suppress_trace = False
        self.reset_result()
        self.entry.focus_set()
        self.set_status("Ready", "muted")

    def copy_text(self, text, status):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except tk.TclError:
            self.set_status("Couldn't access the clipboard.", "danger")
            return False
        self.set_status(status, "success")
        return True

    def copy_result(self):
        if not self.has_result:
            self.set_status("Nothing to copy yet.", "danger")
            return
        if self.copy_text(self.result_text, "Full result copied."):
            self.show_toast("Full result copied")

    def copy_value(self):
        if not self.result_value:
            self.set_status("Nothing to copy yet.", "danger")
            return
        if self.copy_text(self.result_value, "Converted value copied."):
            self.result_label.configure(text=MSG_COPIED)
            self.style_result_text()
            self.show_toast("Value copied")
            if self.copy_flash_job:
                self.root.after_cancel(self.copy_flash_job)
            self.copy_flash_job = self.root.after(900, self.restore_result_text)

    def restore_result_text(self):
        self.copy_flash_job = None
        if self.result_value:
            self.result_label.configure(text=self.result_value)
            self.style_result_text()

    def show_toast(self, text):
        if self.toast and self.toast.winfo_exists():
            self.toast.destroy()
        c = self.colors
        toast = self.toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.configure(bg=c["card"], highlightthickness=1, highlightbackground=c["border"])
        row = tk.Frame(toast, bg=c["card"], bd=0)
        row.pack(fill=tk.BOTH, expand=True, padx=12, pady=9)
        tk.Label(row, text="\u25cf", bg=c["card"], fg=c["green"], font=(self.ui_font, 8)).pack(side=tk.LEFT, padx=(0, 7))
        tk.Label(row, text=text, bg=c["card"], fg=c["text"], font=(self.ui_font, 9, "bold")).pack(side=tk.LEFT)
        toast.update_idletasks()
        self.place_toast()
        toast.after(1200, lambda: self.dismiss_toast(toast))

    def place_toast(self):
        if not self.toast or not self.toast.winfo_exists():
            return
        x = self.root.winfo_x() + self.root.winfo_width() - self.toast.winfo_width() - 24
        y = self.root.winfo_y() + self.root.winfo_height() - self.toast.winfo_height() - 50
        self.toast.geometry(f"+{max(0, x)}+{max(0, y)}")

    @staticmethod
    def dismiss_toast(toast):
        try:
            if toast.winfo_exists():
                toast.destroy()
        except tk.TclError:
            pass

    def set_status(self, message, kind="muted"):
        c = self.colors
        colors_by_kind = {"success": c["green"], "danger": c["red"], "muted": c["muted"], "primary": c["accent"]}
        color = colors_by_kind.get(kind, c["muted"])
        self.status_kind = kind if kind in colors_by_kind else "muted"
        self.status_label.configure(bg=c["bg"], fg=color, text=message)
        self.status_dot.configure(bg=c["bg"], fg=color)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        self.set_status("Fullscreen on." if self.fullscreen else "Fullscreen off.", "success")

    # ---- confirm dialog ---------------------------------------------------

    def ask_confirm(self, title, message):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        c = self.colors
        dialog.configure(bg=c["card"])
        result = {"ok": False}

        frame = tk.Frame(dialog, bg=c["card"], bd=0, highlightthickness=1, highlightbackground=c["border"])
        frame.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(frame, bg=c["card"], bd=0)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
        tk.Label(body, text=title, bg=c["card"], fg=c["text"], font=(self.ui_font, 12, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(
            body, text=message, bg=c["card"], fg=c["muted"], font=(self.ui_font, 9),
            anchor="w", wraplength=280, justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(6, 14))

        buttons = tk.Frame(body, bg=c["card"])
        buttons.pack(fill=tk.X)

        def cancel():
            dialog.destroy()

        def accept():
            result["ok"] = True
            dialog.destroy()

        tk.Button(
            buttons, text="Cancel", command=cancel, bg=c["card"], fg=c["muted"],
            activebackground=c["border"], activeforeground=c["text"], relief=tk.FLAT, bd=0, cursor="hand2", padx=12, pady=7,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        confirm_btn = tk.Button(
            buttons, text="Clear", command=accept, bg=c["red"], fg="white",
            activebackground=c["red"], activeforeground="white", relief=tk.FLAT, bd=0, cursor="hand2", padx=14, pady=7,
        )
        confirm_btn.pack(side=tk.RIGHT)

        dialog.bind("<Escape>", lambda e: cancel())
        dialog.bind("<Return>", lambda e: accept())
        dialog.update_idletasks()
        self.center_window(dialog, dialog.winfo_reqwidth(), dialog.winfo_reqheight())
        confirm_btn.focus_set()
        self.root.wait_window(dialog)
        return result["ok"]

    # ---- settings window --------------------------------------------------

    def open_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        self.theme_before_preview = self.theme
        win = self.settings_win = tk.Toplevel(self.root)
        win.title("Settings")
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self.close_settings)

        frame = self.settings_frame = tk.Frame(win, bd=0)
        frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=20)

        self.settings_title = tk.Label(frame, text="Settings", font=(self.ui_font, 17, "bold"), anchor="w")
        self.settings_title.pack(fill=tk.X, pady=(0, 2))
        self.settings_subtitle = tk.Label(
            frame, text="Change how Weight Converter looks and remembers things.", font=(self.ui_font, 9), anchor="w"
        )
        self.settings_subtitle.pack(fill=tk.X, pady=(0, 16))

        self.theme_label = tk.Label(frame, text="Theme", font=(self.ui_font, 9, "bold"), anchor="w")
        self.theme_label.pack(fill=tk.X, pady=(0, 6))
        self.theme_choice = tk.StringVar(master=self.root, value=self.theme)
        self.theme_row = tk.Frame(frame, bd=0, highlightthickness=1)
        self.theme_row.pack(fill=tk.X, pady=(0, 16))
        self.theme_buttons = {}
        for mode in ("system", "light", "dark"):
            btn = tk.Button(
                self.theme_row, text=mode.title(), command=lambda m=mode: self.preview_theme(m),
                font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", pady=9,
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            btn.bind("<Enter>", self.on_theme_button_hover)
            btn.bind("<Leave>", lambda e: self.theme_settings_window())
            self.theme_buttons[mode] = btn

        self.remember_window_var = tk.BooleanVar(master=self.root, value=self.settings.get("remember_window", True))
        self.remember_unit_var = tk.BooleanVar(master=self.root, value=self.settings.get("remember_unit", True))
        self.remember_history_var = tk.BooleanVar(master=self.root, value=self.settings.get("remember_history", True))
        self.settings_checks = []
        for label, var in (
            ("Remember window size and position", self.remember_window_var),
            ("Remember last selected unit", self.remember_unit_var),
            ("Remember conversion history", self.remember_history_var),
        ):
            check = tk.Checkbutton(
                frame, text=label, variable=var, font=(self.ui_font, 9), anchor="w",
                relief=tk.FLAT, bd=0, highlightthickness=0, cursor="hand2",
            )
            check.pack(fill=tk.X, pady=3)
            self.settings_checks.append(check)

        buttons = self.settings_buttons_row = tk.Frame(frame, bd=0)
        buttons.pack(fill=tk.X, pady=(18, 0))
        self.settings_cancel_btn = tk.Button(
            buttons, text="Cancel", command=self.close_settings,
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=14, pady=7,
        )
        self.settings_cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.settings_save_btn = tk.Button(
            buttons, text="Save", command=self.save_settings_from_dialog,
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=16, pady=7,
        )
        self.settings_save_btn.pack(side=tk.RIGHT)

        self.theme_settings_window()
        win.update_idletasks()
        self.center_window(win, win.winfo_reqwidth(), win.winfo_reqheight())
        win.focus_force()

    def preview_theme(self, mode):
        self.theme_choice.set(mode)
        self.theme = mode
        self.dark = detect_windows_dark_mode() if mode == "system" else mode == "dark"
        self.colors = DARK if self.dark else LIGHT
        self.apply_theme()
        self.theme_settings_window()

    def on_theme_button_hover(self, event):
        btn = event.widget
        mode = next((key for key, value in self.theme_buttons.items() if value is btn), None)
        if mode and mode != self.theme_choice.get():
            btn.configure(bg=self.colors["accent_soft"], fg=self.colors["text"])

    def theme_settings_window(self):
        if not self.settings_win or not self.settings_win.winfo_exists():
            return
        c = self.colors
        self.settings_win.configure(bg=c["card"])
        self.settings_frame.configure(bg=c["card"])
        self.settings_title.configure(bg=c["card"], fg=c["text"])
        self.settings_subtitle.configure(bg=c["card"], fg=c["muted"])
        self.theme_label.configure(bg=c["card"], fg=c["muted"])
        self.theme_row.configure(bg=c["input"], highlightbackground=c["border"], highlightcolor=c["border"])
        for mode, btn in self.theme_buttons.items():
            selected = self.theme_choice.get() == mode
            btn.configure(
                text=f"\u2713  {mode.title()}" if selected else mode.title(),
                bg=c["selected"] if selected else c["input"],
                fg=c["selected_text"] if selected else c["muted"],
                activebackground=c["selected"] if selected else c["accent_soft"],
                activeforeground=c["selected_text"] if selected else c["text"],
            )
        for check in self.settings_checks:
            check.configure(bg=c["card"], fg=c["text"], activebackground=c["card"], activeforeground=c["text"], selectcolor=c["input"])
        self.settings_buttons_row.configure(bg=c["card"])
        self.settings_cancel_btn.configure(bg=c["card"], fg=c["muted"], activebackground=c["border"], activeforeground=c["text"])
        self.settings_save_btn.configure(bg=c["accent"], fg="white", activebackground=c["accent_hover"], activeforeground="white")

    def save_settings_from_dialog(self):
        had_history = self.settings.get("remember_history", True)
        self.settings["remember_window"] = bool(self.remember_window_var.get())
        self.settings["remember_unit"] = bool(self.remember_unit_var.get())
        self.settings["remember_history"] = bool(self.remember_history_var.get())
        self.theme = self.theme_choice.get()
        self.dark = detect_windows_dark_mode() if self.theme == "system" else self.theme == "dark"
        self.colors = DARK if self.dark else LIGHT

        if had_history and not self.settings["remember_history"]:
            self.history.clear()
            try:
                HISTORY_FILE.unlink(missing_ok=True)
            except OSError:
                pass

        self.save_settings()
        self.apply_theme()
        self.close_settings(restore=False)
        self.set_status("Settings saved.", "success")

    def close_settings(self, restore=True):
        if self.settings_win and self.settings_win.winfo_exists():
            if restore and self.theme_before_preview is not None:
                self.theme = self.theme_before_preview
                self.dark = detect_windows_dark_mode() if self.theme == "system" else self.theme == "dark"
                self.colors = DARK if self.dark else LIGHT
                self.apply_theme()
            self.settings_win.destroy()
        self.settings_win = None
        self.theme_before_preview = None
        self.root.focus_force()

    # ---- about window -------------------------------------------------

    def show_about(self):
        if self.about_win and self.about_win.winfo_exists():
            self.about_win.lift()
            self.about_win.focus_force()
            return
        win = self.about_win = tk.Toplevel(self.root)
        win.title("About")
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self.close_about)

        frame = self.about_frame = tk.Frame(win, bd=0)
        frame.pack(fill=tk.BOTH, expand=True, padx=26, pady=24)

        self.about_icon = tk.Label(frame, text="\u2696", font=(self.ui_font, 28))
        self.about_icon.pack(pady=(0, 6))
        self.about_title = tk.Label(frame, text="Weight Converter", font=(self.ui_font, 17, "bold"))
        self.about_title.pack()
        self.about_version = tk.Label(frame, text=f"Version {APP_VERSION}", font=(self.ui_font, 9))
        self.about_version.pack(pady=(3, 12))
        self.about_text = tk.Label(
            frame, text="A small, fast tool for kilogram and pound conversions.",
            font=(self.ui_font, 10), justify=tk.CENTER, wraplength=260,
        )
        self.about_text.pack(pady=(0, 12))
        self.about_formula = tk.Label(frame, text="1 kg = 2.20462 lbs", font=(self.ui_font, 10, "bold"))
        self.about_formula.pack(pady=(0, 16))

        links = self.about_links = tk.Frame(frame, bd=0)
        links.pack(fill=tk.X, pady=(0, 14))
        self.x_link_btn = tk.Button(
            links, text="X   @bardhzzY", command=lambda: self.open_link(TWITTER_URL),
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=12, pady=9,
        )
        self.x_link_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.github_link_btn = tk.Button(
            links, text="GitHub   bardh1xyz", command=lambda: self.open_link(GITHUB_URL),
            font=(self.ui_font, 9, "bold"), relief=tk.FLAT, bd=0, cursor="hand2", padx=12, pady=9,
        )
        self.github_link_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        self.about_footer = tk.Label(frame, text="Made by @bardhzzY", font=(self.ui_font, 8), cursor="hand2")
        self.about_footer.pack(pady=(0, 13))
        self.about_footer.bind("<Button-1>", lambda e: self.open_link(TWITTER_URL))

        self.about_close_btn = tk.Button(
            frame, text="Close", command=self.close_about, font=(self.ui_font, 9, "bold"),
            relief=tk.FLAT, bd=0, cursor="hand2", padx=32, pady=8,
        )
        self.about_close_btn.pack()

        for btn in (self.x_link_btn, self.github_link_btn):
            btn.bind("<Enter>", self.on_about_link_hover)
            btn.bind("<Leave>", self.on_about_link_leave)

        self.theme_about_window()
        win.update_idletasks()
        self.center_window(win, win.winfo_reqwidth(), win.winfo_reqheight())
        win.focus_force()

    def on_about_link_hover(self, event):
        event.widget.configure(bg=self.colors["accent_soft"], fg=self.colors["accent"])

    def on_about_link_leave(self, event):
        event.widget.configure(bg=self.colors["input"], fg=self.colors["text"])

    def theme_about_window(self):
        if not self.about_win or not self.about_win.winfo_exists():
            return
        c = self.colors
        self.about_win.configure(bg=c["card"])
        self.about_frame.configure(bg=c["card"])
        for widget in (self.about_icon, self.about_title, self.about_version, self.about_text, self.about_formula, self.about_footer):
            widget.configure(bg=c["card"])
        self.about_icon.configure(fg=c["accent"])
        self.about_title.configure(fg=c["text"])
        self.about_version.configure(fg=c["muted"])
        self.about_text.configure(fg=c["muted"])
        self.about_formula.configure(fg=c["text"])
        self.about_footer.configure(fg=c["faint"])
        self.about_links.configure(bg=c["card"])
        self.x_link_btn.configure(bg=c["input"], fg=c["text"], activebackground=c["border"], activeforeground=c["text"])
        self.github_link_btn.configure(bg=c["input"], fg=c["text"], activebackground=c["border"], activeforeground=c["text"])
        self.about_close_btn.configure(bg=c["accent"], fg="white", activebackground=c["accent_hover"], activeforeground="white")

    def close_about(self):
        if self.about_win and self.about_win.winfo_exists():
            self.about_win.destroy()
        self.about_win = None
        self.root.focus_force()

    def open_link(self, url):
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            self.set_status("Could not open the link.", "danger")

    # ---- shutdown -----------------------------------------------------

    def on_close(self):
        for job in (self.debounce_job, self.copy_flash_job, self.theme_poll_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        if self.fullscreen:
            self.root.attributes("-fullscreen", False)
        if self.settings.get("remember_window", True):
            try:
                self.settings["geometry"] = self.root.geometry()
            except tk.TclError:
                pass
        self.save_settings()
        self.save_history()
        self.root.destroy()


def main():
    root = tk.Tk()
    WeightConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
