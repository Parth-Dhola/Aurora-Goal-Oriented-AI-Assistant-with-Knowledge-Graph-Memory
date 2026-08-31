"""
Aurora Android App — Markdown Formatter + Soft-Keyboard Avoidance + Multi-Theme
Run: python main.py
Build APK: buildozer android debug
"""
import os
import sys
import re
import threading
import json
import requests
from pathlib import Path

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp

try:
    from websocket import WebSocketApp
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

# Enable Android soft keyboard pan / resize mode
Window.softinput_mode = "below_target"

# ── Config & Server URL Management ───────────────────────────────────────────
CONFIG_FILE = Path(os.path.expanduser("~")) / ".aurora_app_config.json"
DEFAULT_HOST = "http://localhost:8000"


def normalize_url(url: str) -> str:
    """Ensure URL has http:// or https:// prefix and no trailing slash."""
    url = url.strip()
    if not url:
        return DEFAULT_HOST
    if not (url.startswith("http://") or url.startswith("https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"server_url": DEFAULT_HOST, "theme": "aurora"}


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Config] Save error: {e}")


_cfg = load_config()
SERVER_URL = normalize_url(_cfg.get("server_url", DEFAULT_HOST))


def get_api_base() -> str:
    return f"{SERVER_URL}/api"


def get_ws_base() -> str:
    ws_protocol = "wss" if SERVER_URL.startswith("https") else "ws"
    host = SERVER_URL.split("://")[-1]
    return f"{ws_protocol}://{host}/ws"


SESSION_ID = "android-session"


def render_markdown_for_kivy(text: str) -> str:
    """
    Parses LLM Markdown (headings, bold, lists, wikilinks, code blocks)
    into clean, readable Kivy markup without raw markdown symbols (*, #).
    """
    if not text:
        return ""

    # Replace square brackets to prevent Kivy BBCode parse breaks
    text = text.replace("&", "&amp;").replace("[[", "(").replace("]]", ")")

    # Convert Markdown Headings (# Header, ## Header, ### Header) to Bold
    text = re.sub(r'(?m)^#{1,6}\s*(.+)$', r'[b]\1[/b]', text)

    # Convert **bold** or __bold__ to [b]bold[/b]
    text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)
    text = re.sub(r'__(.+?)__', r'[b]\1[/b]', text)

    # Convert *italic* or _italic_ to [i]italic[/i]
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'[i]\1[/i]', text)

    # Convert bullet points (- item or * item) to clean bullet •
    text = re.sub(r'(?m)^[\*\-]\s+', r'• ', text)

    # Convert numbered lists (1. item)
    text = re.sub(r'(?m)^(\d+)\.\s+', r'\1. ', text)

    # Clean backtick inline code `code`
    text = re.sub(r'`([^`]+)`', r'[b]\1[/b]', text)

    # Clean multi-line code fences
    text = re.sub(r'```[a-zA-Z]*\n?([\s\S]*?)```', r'\1', text)

    return text.strip()


# ── Multi-Theme Palettes ──────────────────────────────────────────────────────
THEMES = {
    "aurora": {
        "name": "[ Aurora ]",
        "window_bg":       (0.06, 0.08, 0.14, 1),    # Midnight indigo
        "header_bg":       (0.09, 0.12, 0.20, 1),
        "text_primary":    (0.88, 0.96, 1.0, 1),     # Glowing ice white
        "text_secondary":  (0.42, 0.68, 0.78, 1),    # Aurora teal
        "user_bubble_bg":  (0.12, 0.28, 0.40, 1),    # Deep luminous cyan
        "user_bubble_fg":  (0.40, 0.95, 0.88, 1),
        "ai_bubble_bg":    (0.10, 0.14, 0.23, 1),    # Midnight glass
        "ai_bubble_fg":    (0.92, 0.96, 1.0, 1),
        "input_bg":        (0.10, 0.14, 0.23, 1),
        "input_fg":        (0.95, 0.98, 1.0, 1),
        "chip_bg":         (0.11, 0.16, 0.28, 1),    # Aurora chip
        "chip_fg":         (0.35, 0.88, 0.72, 1),
        "btn_primary":     (0.12, 0.82, 0.62, 1),    # Aurora emerald glow
        "btn_primary_fg":  (0.04, 0.12, 0.10, 1),
        "btn_secondary":   (0.28, 0.55, 0.95, 1),    # Electric blue
        "btn_grey":        (0.15, 0.20, 0.32, 1),
        "btn_grey_fg":     (0.70, 0.85, 0.95, 1),
    },
    "light": {
        "name": "[ Paper ]",
        "window_bg":       (0.96, 0.95, 0.93, 1),    # Warm paper cream (eye-care)
        "header_bg":       (1.0, 1.0, 1.0, 1),
        "text_primary":    (0.13, 0.16, 0.22, 1),    # Deep charcoal
        "text_secondary":  (0.48, 0.53, 0.60, 1),    # Muted slate
        "user_bubble_bg":  (0.86, 0.92, 0.99, 1),    # Soft pastel sky
        "user_bubble_fg":  (0.08, 0.20, 0.38, 1),
        "ai_bubble_bg":    (1.0, 1.0, 1.0, 1),       # Crisp white card
        "ai_bubble_fg":    (0.14, 0.17, 0.22, 1),
        "input_bg":        (1.0, 1.0, 1.0, 1),
        "input_fg":        (0.13, 0.16, 0.22, 1),
        "chip_bg":         (0.90, 0.89, 0.86, 1),    # Warm linen
        "chip_fg":         (0.18, 0.24, 0.32, 1),
        "btn_primary":     (0.24, 0.48, 0.88, 1),    # Calming royal blue
        "btn_primary_fg":  (1.0, 1.0, 1.0, 1),
        "btn_secondary":   (0.28, 0.64, 0.46, 1),    # Soft sage green
        "btn_grey":        (0.88, 0.87, 0.84, 1),
        "btn_grey_fg":     (0.25, 0.30, 0.38, 1),
    },
    "slate": {
        "name": "[ Slate ]",
        "window_bg":       (0.12, 0.14, 0.18, 1),    # Gentle slate charcoal
        "header_bg":       (0.16, 0.19, 0.25, 1),
        "text_primary":    (0.92, 0.94, 0.97, 1),
        "text_secondary":  (0.58, 0.64, 0.72, 1),
        "user_bubble_bg":  (0.20, 0.32, 0.50, 1),
        "user_bubble_fg":  (0.90, 0.95, 1.0, 1),
        "ai_bubble_bg":    (0.18, 0.21, 0.28, 1),
        "ai_bubble_fg":    (0.88, 0.91, 0.95, 1),
        "input_bg":        (0.18, 0.21, 0.28, 1),
        "input_fg":        (0.95, 0.95, 0.95, 1),
        "chip_bg":         (0.22, 0.26, 0.35, 1),
        "chip_fg":         (0.85, 0.90, 0.98, 1),
        "btn_primary":     (0.26, 0.50, 0.90, 1),
        "btn_primary_fg":  (1.0, 1.0, 1.0, 1),
        "btn_secondary":   (0.22, 0.60, 0.42, 1),
        "btn_grey":        (0.22, 0.26, 0.34, 1),
        "btn_grey_fg":     (0.85, 0.90, 0.96, 1),
    }
}

CURRENT_THEME = _cfg.get("theme", "aurora")
if CURRENT_THEME not in THEMES:
    CURRENT_THEME = "aurora"
Window.clearcolor = THEMES[CURRENT_THEME]["window_bg"]


def api_post(endpoint, data, token=None):
    url = f"{get_api_base()}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(url, json=data, headers=headers, timeout=15)
        return r.json()
    except requests.exceptions.ConnectionError:
        return {
            "error": f"Cannot connect to: {SERVER_URL}\n"
                     f"Please ensure the backend is running with --host 0.0.0.0 and you entered your Wi-Fi IP."
        }
    except Exception as e:
        return {"error": str(e)}


class ChatBubble(Label):
    def __init__(self, text, is_user=False, theme_name="aurora", **kwargs):
        super().__init__(**kwargs)
        self.markup = True
        self.text = text if is_user else render_markdown_for_kivy(text)
        self.size_hint_y = None
        self.text_size = (Window.width * 0.78, None)
        self.halign = "right" if is_user else "left"
        self.valign = "middle"
        self.padding = (dp(16), dp(12))
        self.font_size = sp(15)
        
        t = THEMES.get(theme_name, THEMES["aurora"])
        bg_col = t["user_bubble_bg"] if is_user else t["ai_bubble_bg"]
        self.color = t["user_bubble_fg"] if is_user else t["ai_bubble_fg"]

        with self.canvas.before:
            self.rect_color = Color(*bg_col)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])

        self.bind(pos=self._update_rect, size=self._update_rect)
        self.bind(texture_size=self.setter("size"))

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.show_pwd = False
        t = THEMES[CURRENT_THEME]

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(28), dp(36), dp(28), dp(36)],
            spacing=dp(14)
        )
        self.container.bind(minimum_height=self.container.setter("height"))

        # App Logo & Branding
        self.title_lbl = Label(
            text="AURORA",
            font_size=sp(32),
            bold=True,
            size_hint_y=None,
            height=dp(44),
            color=t["text_primary"]
        )
        self.sub_lbl = Label(
            text="Goal-Oriented AI & Knowledge Graph Memory",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(24),
            color=t["text_secondary"]
        )
        self.container.add_widget(self.title_lbl)
        self.container.add_widget(self.sub_lbl)
        self.container.add_widget(Label(size_hint_y=None, height=dp(10)))

        # ── Server URL Settings Box ───────────────────────────────────────────
        server_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(76), spacing=dp(4))
        self.server_lbl = Label(
            text="Backend Server IP (e.g. 192.168.0.128:8000):",
            font_size=sp(12),
            color=t["text_secondary"],
            size_hint_y=None,
            height=dp(18),
            halign="left"
        )
        self.server_lbl.bind(size=self.server_lbl.setter("text_size"))
        
        self.server_input = TextInput(
            text=SERVER_URL,
            multiline=False,
            font_size=sp(15),
            size_hint_y=None,
            height=dp(50),
            background_color=t["input_bg"],
            foreground_color=t["input_fg"],
            padding=[dp(14), dp(13)],
            hint_text="192.168.0.128:8000"
        )
        self.server_input.bind(text=self._on_server_url_change)
        server_box.add_widget(self.server_lbl)
        server_box.add_widget(self.server_input)
        self.container.add_widget(server_box)

        # ── Username Input ────────────────────────────────────────────────────
        self.username_input = TextInput(
            hint_text="Username",
            multiline=False,
            font_size=sp(16),
            size_hint_y=None,
            height=dp(54),
            background_color=t["input_bg"],
            foreground_color=t["input_fg"],
            padding=[dp(16), dp(15)]
        )
        self.container.add_widget(self.username_input)

        # ── Password Input with Show/Hide Toggle ─────────────────────────────
        pwd_box = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
        self.password_input = TextInput(
            hint_text="Password",
            password=True,
            multiline=False,
            font_size=sp(16),
            size_hint_x=0.75,
            background_color=t["input_bg"],
            foreground_color=t["input_fg"],
            padding=[dp(16), dp(15)]
        )
        self.password_input.bind(on_text_validate=self.login)

        self.eye_btn = Button(
            text="SHOW",
            size_hint_x=0.25,
            font_size=sp(13),
            bold=True,
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"]
        )
        self.eye_btn.bind(on_press=self.toggle_show_password)

        pwd_box.add_widget(self.password_input)
        pwd_box.add_widget(self.eye_btn)
        self.container.add_widget(pwd_box)

        # Status Label
        self.status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(42),
            color=(0.95, 0.4, 0.4, 1),
            font_size=sp(13),
            halign="center"
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        self.container.add_widget(self.status_label)

        # Login / Register Action Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(12))
        self.login_btn = Button(
            text="LOGIN",
            background_color=t["btn_primary"],
            background_normal="",
            bold=True,
            font_size=sp(15),
            color=t.get("btn_primary_fg", (1, 1, 1, 1))
        )
        self.login_btn.bind(on_press=self.login)

        self.reg_btn = Button(
            text="REGISTER",
            background_color=t["btn_secondary"],
            background_normal="",
            bold=True,
            font_size=sp(15),
            color=(1, 1, 1, 1)
        )
        self.reg_btn.bind(on_press=self.register)

        btn_row.add_widget(self.login_btn)
        btn_row.add_widget(self.reg_btn)
        self.container.add_widget(btn_row)

        scroll.add_widget(self.container)
        self.add_widget(scroll)

    def _on_server_url_change(self, instance, value):
        global SERVER_URL
        SERVER_URL = normalize_url(value)
        save_config({"server_url": SERVER_URL, "theme": CURRENT_THEME})

    def toggle_show_password(self, instance):
        self.show_pwd = not self.show_pwd
        self.password_input.password = not self.show_pwd
        self.eye_btn.text = "HIDE" if self.show_pwd else "SHOW"

    def login(self, instance):
        threading.Thread(target=self._auth, args=("/auth/login",), daemon=True).start()

    def register(self, instance):
        threading.Thread(target=self._auth, args=("/auth/register",), daemon=True).start()

    def _auth(self, endpoint):
        global SERVER_URL
        SERVER_URL = normalize_url(self.server_input.text)
        username = self.username_input.text.strip()
        password = self.password_input.text.strip()
        if not username or not password:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", "Please enter username & password"), 0)
            return

        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"Connecting to {SERVER_URL}..."), 0)
        result = api_post(endpoint, {"username": username, "password": password})
        if "access_token" in result:
            app = App.get_running_app()
            app.token = result["access_token"]
            app.username = result["username"]
            save_config({"server_url": SERVER_URL, "theme": CURRENT_THEME})
            Clock.schedule_once(lambda dt: self._go_to_chat(), 0)
        else:
            error = result.get("detail", result.get("error", "Authentication failed"))
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", error), 0)

    def _go_to_chat(self):
        chat = self.manager.get_screen("chat")
        chat.on_enter_setup()
        self.manager.current = "chat"


class ChatScreen(Screen):

    SUGGESTIONS = [
        ("Plan Day",       "Plan my day. What should I focus on given my current goals?"),
        ("My Goals",       "What are my current goals and how am I doing on each?"),
        ("Study Notes",    "Summarize the key concepts from my uploaded notes."),
        ("Progress",       "Give me a progress summary across all my goals."),
        ("What to Study?", "What should I study or work on today?"),
        ("Motivate Me",    "Give me a short motivational push for today."),
        ("Weak Areas",     "What are my weakest areas that I should improve?"),
        ("Weekly Review",  "Give me a weekly review of what I've accomplished."),
    ]

    THEME_KEYS = ["aurora", "light", "slate"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ws = None
        self.thinking_bubble = None
        self.theme_mode = CURRENT_THEME
        t = THEMES[self.theme_mode]

        self.root_layout = BoxLayout(orientation="vertical")

        # ── Header ────────────────────────────────────────────────────────────
        header = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(16), dp(8)], spacing=dp(8))
        self.header_title = Label(
            text="Aurora",
            font_size=sp(19),
            bold=True,
            color=t["text_primary"],
            halign="left",
            size_hint_x=0.45
        )
        self.header_title.bind(size=self.header_title.setter("text_size"))

        self.conn_status = Label(
            text="Connecting...",
            font_size=sp(12),
            color=t["text_secondary"],
            halign="center",
            size_hint_x=0.25
        )
        
        # Theme toggle button
        self.theme_btn = Button(
            text=t["name"],
            size_hint=(None, None),
            size=(dp(96), dp(38)),
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"],
            font_size=sp(12),
            bold=True
        )
        self.theme_btn.bind(on_press=self.cycle_theme)

        header.add_widget(self.header_title)
        header.add_widget(self.conn_status)
        header.add_widget(self.theme_btn)
        self.root_layout.add_widget(header)

        # ── Chat area ─────────────────────────────────────────────────────────
        self.chat_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=[dp(14), dp(12)])
        self.chat_layout.bind(minimum_height=self.chat_layout.setter("height"))
        self.scroll = ScrollView(size_hint_y=1)
        self.scroll.add_widget(self.chat_layout)
        self.root_layout.add_widget(self.scroll)

        # ── Suggestion chips ──────────────────────────────────────────────────
        chips_scroll = ScrollView(
            size_hint_y=None,
            height=dp(48),
            do_scroll_y=False,
            do_scroll_x=True,
            bar_width=0
        )
        self.chips_row = BoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            height=dp(48),
            spacing=dp(8),
            padding=[dp(8), dp(4)]
        )
        self.chips_row.bind(minimum_width=self.chips_row.setter("width"))
        self.chip_buttons = []
        for label, message in self.SUGGESTIONS:
            chip = Button(
                text=label,
                size_hint=(None, None),
                width=len(label) * dp(8) + dp(32),
                height=dp(38),
                background_color=t["chip_bg"],
                background_normal="",
                color=t["chip_fg"],
                font_size=sp(13),
            )
            chip.bind(on_press=self._make_chip_handler(message))
            self.chip_buttons.append(chip)
            self.chips_row.add_widget(chip)
        chips_scroll.add_widget(self.chips_row)
        self.root_layout.add_widget(chips_scroll)

        # ── Input row ─────────────────────────────────────────────────────────
        input_row = BoxLayout(size_hint_y=None, height=dp(64), padding=[dp(8), dp(6)], spacing=dp(6))
        
        self.attach_btn = Button(
            text="+ DOC",
            size_hint_x=0.20,
            font_size=sp(13),
            bold=True,
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"]
        )
        self.attach_btn.bind(on_press=self.open_file_picker)

        self.text_input = TextInput(
            hint_text="Message Aurora...",
            multiline=False,
            font_size=sp(16),
            size_hint_x=0.62,
            background_color=t["input_bg"],
            foreground_color=t["input_fg"],
            padding=[dp(14), dp(14)]
        )
        self.text_input.bind(on_text_validate=self.send_message)

        self.send_btn = Button(
            text="SEND",
            size_hint_x=0.18,
            font_size=sp(13),
            bold=True,
            background_color=t["btn_primary"],
            background_normal="",
            color=t.get("btn_primary_fg", (1, 1, 1, 1))
        )
        self.send_btn.bind(on_press=self.send_message)

        input_row.add_widget(self.attach_btn)
        input_row.add_widget(self.text_input)
        input_row.add_widget(self.send_btn)
        self.root_layout.add_widget(input_row)

        # Bottom spacer dynamically expands when Android soft-keyboard appears
        self.bottom_spacer = Label(size_hint_y=None, height=0)
        self.root_layout.add_widget(self.bottom_spacer)

        self.add_widget(self.root_layout)

        # Bind keyboard height changes
        Window.bind(keyboard_height=self._on_keyboard_height)

    def _on_keyboard_height(self, window, height):
        """Float input box smoothly above Android soft keyboard."""
        self.bottom_spacer.height = max(0, height)
        if height > 0:
            Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def cycle_theme(self, instance=None):
        """Cycle through: [ Aurora ] -> [ Paper ] -> [ Slate ]."""
        idx = self.THEME_KEYS.index(self.theme_mode)
        self.theme_mode = self.THEME_KEYS[(idx + 1) % len(self.THEME_KEYS)]
        global CURRENT_THEME
        CURRENT_THEME = self.theme_mode
        save_config({"server_url": SERVER_URL, "theme": CURRENT_THEME})

        t = THEMES[self.theme_mode]
        Window.clearcolor = t["window_bg"]
        
        self.header_title.color = t["text_primary"]
        self.conn_status.color = t["text_secondary"]
        self.theme_btn.text = t["name"]
        self.theme_btn.background_color = t["btn_grey"]
        self.theme_btn.color = t["btn_grey_fg"]

        self.attach_btn.background_color = t["btn_grey"]
        self.attach_btn.color = t["btn_grey_fg"]
        self.text_input.background_color = t["input_bg"]
        self.text_input.foreground_color = t["input_fg"]
        self.send_btn.background_color = t["btn_primary"]
        self.send_btn.color = t.get("btn_primary_fg", (1, 1, 1, 1))

        for chip in self.chip_buttons:
            chip.background_color = t["chip_bg"]
            chip.color = t["chip_fg"]

    def _make_chip_handler(self, message: str):
        def handler(instance):
            self.text_input.text = message
            Clock.schedule_once(lambda dt: self.send_message(instance), 0.05)
        return handler

    def open_file_picker(self, instance):
        """Open a file chooser popup to upload PDF / TXT study materials."""
        t = THEMES[self.theme_mode]
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        filechooser = FileChooserListView(
            path=os.path.expanduser("~"),
            filters=["*.pdf", "*.txt", "*.PDF", "*.TXT"]
        )
        content.add_widget(filechooser)

        btn_bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        cancel_btn = Button(
            text="Cancel",
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"],
            font_size=sp(14)
        )
        upload_btn = Button(
            text="Upload to KG",
            background_color=t["btn_primary"],
            background_normal="",
            color=t.get("btn_primary_fg", (1, 1, 1, 1)),
            bold=True,
            font_size=sp(14)
        )

        popup = Popup(
            title="Select Study PDF or Notes",
            content=content,
            size_hint=(0.92, 0.85),
            background_color=t["header_bg"]
        )
        cancel_btn.bind(on_press=popup.dismiss)

        def do_upload(btn_instance):
            selected = filechooser.selection
            if not selected:
                return
            popup.dismiss()
            filepath = selected[0]
            self.upload_file(filepath)

        upload_btn.bind(on_press=do_upload)
        btn_bar.add_widget(cancel_btn)
        btn_bar.add_widget(upload_btn)
        content.add_widget(btn_bar)

        popup.open()

    def upload_file(self, filepath):
        filename = os.path.basename(filepath)
        self.add_bubble(f"Uploading '{filename}' into Knowledge Graph...", True)

        def _worker():
            app = App.get_running_app()
            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                files = {"file": (filename, file_bytes, "application/pdf" if filename.lower().endswith(".pdf") else "text/plain")}
                r = requests.post(
                    f"{get_api_base()}/documents/upload",
                    files=files,
                    headers={"Authorization": f"Bearer {app.token}"},
                    timeout=60
                )
                if r.status_code == 200:
                    data = r.json().get("document", {})
                    topics = data.get("topics_created", 1)
                    title = data.get("title", filename)
                    msg = f"'{title}' decomposed into {topics} topic notes & linked into your Knowledge Graph!"
                    Clock.schedule_once(lambda dt: self.add_bubble(msg, False), 0)
                else:
                    err = r.json().get("detail", "Upload failed")
                    Clock.schedule_once(lambda dt: self.add_bubble(f"Upload failed: {err}", False), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.add_bubble(f"Upload error: {str(e)}", False), 0)

        threading.Thread(target=_worker, daemon=True).start()

    def on_enter_setup(self):
        app = App.get_running_app()
        self.header_title.text = f"Aurora — {app.username}"
        self.add_bubble("Hey! I'm Aurora. Connecting...", False)
        self._connect_ws()

    def _connect_ws(self):
        if not WS_AVAILABLE:
            self.add_bubble("Install websocket-client: pip install websocket-client", False)
            return
        app = App.get_running_app()
        url = f"{get_ws_base()}/chat?token={app.token}"
        self.ws = WebSocketApp(
            url,
            on_open=self._ws_open,
            on_message=self._ws_message,
            on_error=self._ws_error,
            on_close=self._ws_close
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _ws_open(self, ws):
        Clock.schedule_once(lambda dt: setattr(self.conn_status, "text", "Connected"), 0)

    def _ws_message(self, ws, raw):
        try:
            data = json.loads(raw)
            t = data.get("type")
            if t == "connected":
                Clock.schedule_once(lambda dt: self.add_bubble("Connected! Ask me anything.", False), 0)
            elif t == "thinking":
                Clock.schedule_once(lambda dt: self._show_thinking(), 0)
            elif t == "message":
                reply = data.get("reply", "")
                Clock.schedule_once(lambda dt: self._show_reply(reply), 0)
            elif t == "error":
                detail = data.get("detail", "Unknown error")
                Clock.schedule_once(lambda dt: self._show_reply(f"Error: {detail}"), 0)
        except Exception as e:
            print(f"[WS] Parse error: {e}")

    def _ws_error(self, ws, error):
        Clock.schedule_once(lambda dt: setattr(self.conn_status, "text", "Error"), 0)

    def _ws_close(self, ws, code, msg):
        Clock.schedule_once(lambda dt: setattr(self.conn_status, "text", "Disconnected"), 0)

    def add_bubble(self, text, is_user):
        bubble = ChatBubble(text=text, is_user=is_user, theme_name=self.theme_mode)
        self.chat_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def _show_thinking(self):
        self.thinking_bubble = ChatBubble(text="Aurora is thinking...", is_user=False, theme_name=self.theme_mode)
        self.chat_layout.add_widget(self.thinking_bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def _show_reply(self, reply):
        if self.thinking_bubble and self.thinking_bubble.parent:
            self.chat_layout.remove_widget(self.thinking_bubble)
            self.thinking_bubble = None
        self.add_bubble(reply, False)

    def send_message(self, instance):
        msg = self.text_input.text.strip()
        if not msg:
            return
        self.text_input.text = ""
        self.add_bubble(msg, True)
        if self.ws:
            try:
                self.ws.send(json.dumps({"message": msg, "session_id": SESSION_ID}))
            except Exception as e:
                self.add_bubble(f"Send failed: {e}", False)
        else:
            self.add_bubble("Not connected.", False)


class AuroraApp(App):
    token = None
    username = None
    def build(self):
        self.title = "Aurora"
        sm = ScreenManager(transition=FadeTransition())
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(ChatScreen(name="chat"))
        return sm


if __name__ == "__main__":
    AuroraApp().run()
