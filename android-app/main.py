"""
Aurora Android App — Eye-Care Themes + WebSocket + Hybrid GraphRAG Document Upload
Run: python main.py
Build APK: buildozer android debug
"""
import os
import threading
import json
import requests
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

try:
    from websocket import WebSocketApp
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

API_BASE   = "http://localhost:8000/api"
WS_BASE    = "ws://localhost:8000/ws"
SESSION_ID = "android-session"

# ── Eye-Care Theme Palettes ───────────────────────────────────────────────────
THEMES = {
    "light": {
        "name": "☀️ Warm Paper",
        "window_bg":       (0.96, 0.95, 0.93, 1),    # Soft warm paper cream
        "header_bg":       (1.0, 1.0, 1.0, 1),
        "text_primary":    (0.13, 0.16, 0.22, 1),    # Deep charcoal
        "text_secondary":  (0.48, 0.53, 0.60, 1),    # Muted slate
        "user_bubble_bg":  (0.86, 0.92, 0.99, 1),    # Soft pastel sky
        "user_bubble_fg":  (0.08, 0.20, 0.38, 1),
        "ai_bubble_bg":    (1.0, 1.0, 1.0, 1),       # Pure crisp white card
        "ai_bubble_fg":    (0.14, 0.17, 0.22, 1),
        "input_bg":        (1.0, 1.0, 1.0, 1),
        "input_fg":        (0.13, 0.16, 0.22, 1),
        "chip_bg":         (0.90, 0.89, 0.86, 1),    # Warm linen
        "chip_fg":         (0.18, 0.24, 0.32, 1),
        "btn_primary":     (0.24, 0.48, 0.88, 1),    # Calming royal blue
        "btn_secondary":   (0.28, 0.64, 0.46, 1),    # Soft sage green
        "btn_grey":        (0.88, 0.87, 0.84, 1),
        "btn_grey_fg":     (0.25, 0.30, 0.38, 1),
    },
    "dark": {
        "name": "🌙 Soft Slate",
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
        "btn_secondary":   (0.22, 0.60, 0.42, 1),
        "btn_grey":        (0.22, 0.26, 0.34, 1),
        "btn_grey_fg":     (0.85, 0.90, 0.96, 1),
    }
}

CURRENT_THEME = "light"
Window.clearcolor = THEMES[CURRENT_THEME]["window_bg"]


def api_post(endpoint, data, token=None):
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect. Check server IP and port."}
    except Exception as e:
        return {"error": str(e)}


class ChatBubble(Label):
    def __init__(self, text, is_user=False, theme_name="light", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.size_hint_y = None
        self.text_size = (Window.width * 0.76, None)
        self.halign = "right" if is_user else "left"
        self.valign = "middle"
        self.padding = (16, 12)
        
        t = THEMES.get(theme_name, THEMES["light"])
        bg_col = t["user_bubble_bg"] if is_user else t["ai_bubble_bg"]
        self.color = t["user_bubble_fg"] if is_user else t["ai_bubble_fg"]

        with self.canvas.before:
            self.rect_color = Color(*bg_col)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12, 12, 12, 12])

        self.bind(pos=self._update_rect, size=self._update_rect)
        self.bind(texture_size=self.setter("size"))

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=[40, 60, 40, 40], spacing=16)
        
        self.layout.add_widget(Label(text="🌟", font_size=52, size_hint_y=None, height=70))
        self.title_lbl = Label(text="Aurora", font_size=34, bold=True,
                               size_hint_y=None, height=50, color=THEMES["light"]["text_primary"])
        self.sub_lbl = Label(text="Your personal AI assistant & Knowledge Graph", font_size=14,
                             size_hint_y=None, height=30, color=THEMES["light"]["text_secondary"])
        self.layout.add_widget(self.title_lbl)
        self.layout.add_widget(self.sub_lbl)
        self.layout.add_widget(Label(size_hint_y=None, height=20))

        t = THEMES[CURRENT_THEME]
        self.username_input = TextInput(hint_text="Username", multiline=False,
            size_hint_y=None, height=52, background_color=t["input_bg"],
            foreground_color=t["input_fg"], padding=[14,14])
        self.layout.add_widget(self.username_input)

        self.password_input = TextInput(hint_text="Password", password=True,
            multiline=False, size_hint_y=None, height=52, background_color=t["input_bg"],
            foreground_color=t["input_fg"], padding=[14,14])
        self.password_input.bind(on_text_validate=self.login)
        self.layout.add_widget(self.password_input)

        self.status_label = Label(text="", size_hint_y=None, height=28,
                                  color=(0.85, 0.3, 0.3, 1), font_size=13)
        self.layout.add_widget(self.status_label)

        btn_row = BoxLayout(size_hint_y=None, height=52, spacing=12)
        login_btn = Button(text="Login", background_color=t["btn_primary"], background_normal="", bold=True)
        login_btn.bind(on_press=self.login)
        reg_btn = Button(text="Register", background_color=t["btn_secondary"], background_normal="", bold=True)
        reg_btn.bind(on_press=self.register)
        btn_row.add_widget(login_btn)
        btn_row.add_widget(reg_btn)
        self.layout.add_widget(btn_row)

        self.add_widget(self.layout)

    def login(self, instance):
        threading.Thread(target=self._auth, args=("/auth/login",), daemon=True).start()

    def register(self, instance):
        threading.Thread(target=self._auth, args=("/auth/register",), daemon=True).start()

    def _auth(self, endpoint):
        username = self.username_input.text.strip()
        password = self.password_input.text.strip()
        if not username or not password:
            Clock.schedule_once(lambda dt: setattr(self.status_label,"text","Enter username and password"),0)
            return
        Clock.schedule_once(lambda dt: setattr(self.status_label,"text","Connecting..."),0)
        result = api_post(endpoint, {"username": username, "password": password})
        if "access_token" in result:
            app = App.get_running_app()
            app.token = result["access_token"]
            app.username = result["username"]
            Clock.schedule_once(lambda dt: self._go_to_chat(), 0)
        else:
            error = result.get("detail", result.get("error","Authentication failed"))
            Clock.schedule_once(lambda dt: setattr(self.status_label,"text",error),0)

    def _go_to_chat(self):
        chat = self.manager.get_screen("chat")
        chat.on_enter_setup()
        self.manager.current = "chat"


class ChatScreen(Screen):

    SUGGESTIONS = [
        ("📋 Plan my day",       "Plan my day. What should I focus on given my current goals?"),
        ("🎯 Show my goals",     "What are my current goals and how am I doing on each?"),
        ("📚 Search notes",      "Summarize the key concepts from my uploaded notes."),
        ("📊 My progress",       "Give me a progress summary across all my goals."),
        ("📚 What to study?",    "What should I study or work on today?"),
        ("💪 Motivate me",       "Give me a short motivational push for today."),
        ("⚠️  Weak areas",       "What are my weakest areas that I should improve?"),
        ("🗓️  Weekly review",    "Give me a weekly review of what I've accomplished."),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ws = None
        self.thinking_bubble = None
        self.theme_mode = CURRENT_THEME
        self.bubbles = []
        t = THEMES[self.theme_mode]

        root = BoxLayout(orientation="vertical")

        # ── Header ────────────────────────────────────────────────────────────
        header = BoxLayout(size_hint_y=None, height=56, padding=[16,8], spacing=8)
        self.header_title = Label(text="Aurora", font_size=19, bold=True,
                                  color=t["text_primary"], halign="left", size_hint_x=0.45)
        self.conn_status = Label(text="⚪ Connecting...", font_size=12,
                                 color=t["text_secondary"], halign="center", size_hint_x=0.30)
        
        # Theme toggle button
        self.theme_btn = Button(text="🌙 Theme", size_hint=(None, None), size=(90, 36),
                                background_color=t["btn_grey"], background_normal="",
                                color=t["btn_grey_fg"], font_size=12)
        self.theme_btn.bind(on_press=self.toggle_theme)

        header.add_widget(self.header_title)
        header.add_widget(self.conn_status)
        header.add_widget(self.theme_btn)
        root.add_widget(header)

        # ── Chat area ─────────────────────────────────────────────────────────
        self.chat_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=8, padding=[12,12])
        self.chat_layout.bind(minimum_height=self.chat_layout.setter("height"))
        self.scroll = ScrollView(size_hint_y=1)
        self.scroll.add_widget(self.chat_layout)
        root.add_widget(self.scroll)

        # ── Suggestion chips ──────────────────────────────────────────────────
        chips_scroll = ScrollView(size_hint_y=None, height=46,
                                  do_scroll_y=False, do_scroll_x=True,
                                  bar_width=0)
        self.chips_row = BoxLayout(orientation="horizontal", size_hint_x=None,
                                   height=46, spacing=8, padding=[8, 5])
        self.chips_row.bind(minimum_width=self.chips_row.setter("width"))
        self.chip_buttons = []
        for label, message in self.SUGGESTIONS:
            chip = Button(
                text=label,
                size_hint=(None, None),
                width=len(label) * 9 + 24,
                height=36,
                background_color=t["chip_bg"],
                background_normal="",
                color=t["chip_fg"],
                font_size=13,
            )
            chip.bind(on_press=self._make_chip_handler(message))
            self.chip_buttons.append(chip)
            self.chips_row.add_widget(chip)
        chips_scroll.add_widget(self.chips_row)
        root.add_widget(chips_scroll)

        # ── Input row ─────────────────────────────────────────────────────────
        input_row = BoxLayout(size_hint_y=None, height=60, padding=[8,6], spacing=6)
        
        self.attach_btn = Button(text="📎", size_hint_x=0.14, font_size=20,
                                 background_color=t["btn_grey"], background_normal="",
                                 color=t["btn_grey_fg"])
        self.attach_btn.bind(on_press=self.open_file_picker)

        self.text_input = TextInput(hint_text="Message Aurora...", multiline=False,
            size_hint_x=0.72, background_color=t["input_bg"],
            foreground_color=t["input_fg"], padding=[12,12])
        self.text_input.bind(on_text_validate=self.send_message)

        self.send_btn = Button(text="➤", size_hint_x=0.14, font_size=20,
                               background_color=t["btn_primary"], background_normal="")
        self.send_btn.bind(on_press=self.send_message)

        input_row.add_widget(self.attach_btn)
        input_row.add_widget(self.text_input)
        input_row.add_widget(self.send_btn)
        root.add_widget(input_row)
        self.add_widget(root)

    def toggle_theme(self, instance=None):
        """Toggle between Eye-Care Warm Paper (Light) and Eye-Care Slate (Dark)."""
        self.theme_mode = "dark" if self.theme_mode == "light" else "light"
        t = THEMES[self.theme_mode]
        Window.clearcolor = t["window_bg"]
        
        self.header_title.color = t["text_primary"]
        self.conn_status.color = t["text_secondary"]
        self.theme_btn.text = "☀️ Light" if self.theme_mode == "dark" else "🌙 Dark"
        self.theme_btn.background_color = t["btn_grey"]
        self.theme_btn.color = t["btn_grey_fg"]

        self.attach_btn.background_color = t["btn_grey"]
        self.attach_btn.color = t["btn_grey_fg"]
        self.text_input.background_color = t["input_bg"]
        self.text_input.foreground_color = t["input_fg"]
        self.send_btn.background_color = t["btn_primary"]

        for chip in self.chip_buttons:
            chip.background_color = t["chip_bg"]
            chip.color = t["chip_fg"]

    def _make_chip_handler(self, message: str):
        def handler(instance):
            self.text_input.text = message
            Clock.schedule_once(lambda dt: self.send_message(instance), 0.05)
        return handler

    def open_file_picker(self, instance):
        """Open an eye-friendly file chooser popup to upload PDF / TXT study materials."""
        t = THEMES[self.theme_mode]
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        filechooser = FileChooserListView(
            path=os.path.expanduser("~"),
            filters=["*.pdf", "*.txt", "*.PDF", "*.TXT"]
        )
        content.add_widget(filechooser)

        btn_bar = BoxLayout(size_hint_y=None, height=44, spacing=10)
        cancel_btn = Button(text="Cancel", background_color=t["btn_grey"], background_normal="", color=t["btn_grey_fg"])
        upload_btn = Button(text="Upload to KG 🚀", background_color=t["btn_primary"], background_normal="", bold=True)

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
        self.add_bubble(f"📄 Uploading '{filename}' into Knowledge Graph...", True)

        def _worker():
            app = App.get_running_app()
            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                files = {"file": (filename, file_bytes, "application/pdf" if filename.lower().endswith(".pdf") else "text/plain")}
                r = requests.post(
                    f"{API_BASE}/documents/upload",
                    files=files,
                    headers={"Authorization": f"Bearer {app.token}"},
                    timeout=60
                )
                if r.status_code == 200:
                    data = r.json().get("document", {})
                    topics = data.get("topics_created", 1)
                    title = data.get("title", filename)
                    msg = f"✅ '{title}' decomposed into {topics} topic notes & linked into your Knowledge Graph!"
                    Clock.schedule_once(lambda dt: self.add_bubble(msg, False), 0)
                else:
                    err = r.json().get("detail", "Upload failed")
                    Clock.schedule_once(lambda dt: self.add_bubble(f"⚠️ Upload failed: {err}", False), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.add_bubble(f"⚠️ Upload error: {str(e)}", False), 0)

        threading.Thread(target=_worker, daemon=True).start()

    def on_enter_setup(self):
        app = App.get_running_app()
        self.header_title.text = f"Aurora — {app.username}"
        self.add_bubble("👋 Hey! I'm Aurora. Connecting...", False)
        self._connect_ws()

    def _connect_ws(self):
        if not WS_AVAILABLE:
            self.add_bubble("Install websocket-client: pip install websocket-client", False)
            return
        app = App.get_running_app()
        url = f"{WS_BASE}/chat?token={app.token}"
        self.ws = WebSocketApp(url,
            on_open=self._ws_open, on_message=self._ws_message,
            on_error=self._ws_error, on_close=self._ws_close)
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _ws_open(self, ws):
        Clock.schedule_once(lambda dt: setattr(self.conn_status,"text","🟢 Connected"),0)

    def _ws_message(self, ws, raw):
        try:
            data = json.loads(raw)
            t = data.get("type")
            if t == "connected":
                Clock.schedule_once(lambda dt: self.add_bubble("✅ Connected! Ask me anything.",False),0)
            elif t == "thinking":
                Clock.schedule_once(lambda dt: self._show_thinking(),0)
            elif t == "message":
                reply = data.get("reply","")
                Clock.schedule_once(lambda dt: self._show_reply(reply),0)
            elif t == "error":
                detail = data.get("detail","Unknown error")
                Clock.schedule_once(lambda dt: self._show_reply(f"⚠️ {detail}"),0)
        except Exception as e:
            print(f"[WS] Parse error: {e}")

    def _ws_error(self, ws, error):
        Clock.schedule_once(lambda dt: setattr(self.conn_status,"text","🔴 Error"),0)

    def _ws_close(self, ws, code, msg):
        Clock.schedule_once(lambda dt: setattr(self.conn_status,"text","⚪ Disconnected"),0)

    def add_bubble(self, text, is_user):
        bubble = ChatBubble(text=text, is_user=is_user, theme_name=self.theme_mode)
        self.chat_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll,"scroll_y",0),0.1)

    def _show_thinking(self):
        self.thinking_bubble = ChatBubble(text="Aurora is thinking... 💭", is_user=False, theme_name=self.theme_mode)
        self.chat_layout.add_widget(self.thinking_bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll,"scroll_y",0),0.1)

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
                self.add_bubble(f"⚠️ Send failed: {e}", False)
        else:
            self.add_bubble("⚠️ Not connected.", False)


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
