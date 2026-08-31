"""
ui/screens/chat.py — Real-Time Chat, Model Switcher & Document Ingestion Screen for Aurora
"""
import os
import threading
import json
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp, sp

try:
    from websocket import WebSocketApp
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

from core.config import CURRENT_THEME, SESSION_ID, get_ws_base, set_theme
from core.api import api_upload_document, api_post, api_get
from ui.theme import THEMES
from ui.components.bubble import ChatBubble
from ui.components.file_picker import DocumentPickerDialog


class StatusDot(Widget):
    """Vector-rendered OpenGL connection indicator dot (100% font-independent)."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(14), dp(14))
        with self.canvas:
            self.color_inst = Color(0.95, 0.78, 0.20, 1) # Amber (Connecting)
            self.circle = Ellipse(pos=self.pos, size=(dp(10), dp(10)))
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.circle.pos = (self.x + (self.width - dp(10)) / 2, self.y + (self.height - dp(10)) / 2)
        self.circle.size = (dp(10), dp(10))

    def set_connected(self):
        self.color_inst.rgba = (0.18, 0.88, 0.44, 1) # Green

    def set_connecting(self):
        self.color_inst.rgba = (0.95, 0.78, 0.20, 1) # Amber

    def set_disconnected(self):
        self.color_inst.rgba = (0.95, 0.30, 0.30, 1) # Red


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
        self.active_llm = "GEMINI"
        t = THEMES[self.theme_mode]

        self.root_layout = BoxLayout(orientation="vertical")

        # ── Header (Vertically Centered & Aligned) ────────────────────────────
        header = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            padding=[dp(10), dp(8)],
            spacing=dp(6)
        )

        # Left branding block: Status Dot + App Title
        left_block = BoxLayout(
            size_hint_x=0.32,
            spacing=dp(6),
            pos_hint={"center_y": 0.5}
        )
        self.status_dot = StatusDot(pos_hint={"center_y": 0.5})
        self.header_title = Label(
            text="Aurora",
            font_size=sp(17),
            bold=True,
            color=t["text_primary"],
            halign="left",
            valign="middle",
            pos_hint={"center_y": 0.5}
        )
        self.header_title.bind(size=self.header_title.setter("text_size"))
        left_block.add_widget(self.status_dot)
        left_block.add_widget(self.header_title)

        # Right control block: Model Switcher + Theme Toggle + Logout
        self.model_btn = Button(
            text="[ GEMINI ]",
            size_hint=(None, None),
            size=(dp(84), dp(36)),
            pos_hint={"center_y": 0.5},
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"],
            font_size=sp(11),
            bold=True
        )
        self.model_btn.bind(on_press=self.open_model_picker)

        self.theme_btn = Button(
            text=f"[ {t['name'].upper()} ]",
            size_hint=(None, None),
            size=(dp(84), dp(36)),
            pos_hint={"center_y": 0.5},
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"],
            font_size=sp(11),
            bold=True
        )
        self.theme_btn.bind(on_press=self.cycle_theme)

        self.logout_btn = Button(
            text="LOGOUT",
            size_hint=(None, None),
            size=(dp(68), dp(36)),
            pos_hint={"center_y": 0.5},
            background_color=t["btn_grey"],
            background_normal="",
            color=(0.95, 0.40, 0.40, 1),
            font_size=sp(10),
            bold=True
        )
        self.logout_btn.bind(on_press=self.logout)

        header.add_widget(left_block)
        header.add_widget(self.model_btn)
        header.add_widget(self.theme_btn)
        header.add_widget(self.logout_btn)
        self.root_layout.add_widget(header)

        # ── Chat message area ──────────────────────────────────────────────────
        self.chat_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=[dp(14), dp(12)])
        self.chat_layout.bind(minimum_height=self.chat_layout.setter("height"))
        self.scroll = ScrollView(size_hint_y=1)
        self.scroll.add_widget(self.chat_layout)
        self.root_layout.add_widget(self.scroll)

        # ── Suggestion chips row ──────────────────────────────────────────────
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
                bold=True
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

        # Dynamic bottom spacer for soft-keyboard avoidance
        self.bottom_spacer = Label(size_hint_y=None, height=0)
        self.root_layout.add_widget(self.bottom_spacer)

        self.add_widget(self.root_layout)

        # Bind keyboard height changes
        Window.bind(keyboard_height=self._on_keyboard_height)

    def _on_keyboard_height(self, window, height):
        """Lift input box smoothly above Android soft keyboard."""
        self.bottom_spacer.height = max(0, height)
        if height > 0:
            Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def logout(self, instance=None):
        """Disconnect WebSocket, reset user session and return to Login Screen."""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        app = App.get_running_app()
        app.token = None
        app.username = None
        self.chat_layout.clear_widgets()
        self.manager.current = "login"

    def cycle_theme(self, instance=None):
        """Cycle through: [ AURORA ] -> [ PAPER ] -> [ SLATE ]."""
        idx = self.THEME_KEYS.index(self.theme_mode)
        self.theme_mode = self.THEME_KEYS[(idx + 1) % len(self.THEME_KEYS)]
        set_theme(self.theme_mode)

        t = THEMES[self.theme_mode]
        Window.clearcolor = t["window_bg"]
        
        self.header_title.color = t["text_primary"]
        self.theme_btn.text = f"[ {t['name'].upper()} ]"
        self.theme_btn.background_color = t["btn_grey"]
        self.theme_btn.color = t["btn_grey_fg"]

        self.model_btn.background_color = t["btn_grey"]
        self.model_btn.color = t["btn_grey_fg"]

        self.logout_btn.background_color = t["btn_grey"]

        self.attach_btn.background_color = t["btn_grey"]
        self.attach_btn.color = t["btn_grey_fg"]
        self.text_input.background_color = t["input_bg"]
        self.text_input.foreground_color = t["input_fg"]
        self.send_btn.background_color = t["btn_primary"]
        self.send_btn.color = t.get("btn_primary_fg", (1, 1, 1, 1))

        for chip in self.chip_buttons:
            chip.background_color = t["chip_bg"]
            chip.color = t["chip_fg"]

    def open_model_picker(self, instance):
        """Open popup allowing user to switch LLM provider and model."""
        t = THEMES[self.theme_mode]
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))

        title = Label(
            text="Select Active AI Brain",
            font_size=sp(16),
            bold=True,
            size_hint_y=None,
            height=dp(28),
            color=t["text_primary"]
        )
        content.add_widget(title)

        models = [
            ("Google Gemini (Flash Lite)", "gemini", "gemini-3.1-flash-lite"),
            ("Local LLM (qwen3.5-2b)", "local", "qwen3.5-2b"),
            ("Groq (Llama-3.3-70B)", "groq", "llama-3.3-70b-versatile"),
            ("OpenAI (GPT-4o-mini)", "openai", "gpt-4o-mini"),
            ("Anthropic (Claude 3.5 Sonnet)", "anthropic", "claude-3-5-sonnet-20241022"),
        ]

        popup = Popup(
            title="AI Brain Settings",
            content=content,
            size_hint=(0.92, 0.65),
            background_color=t["header_bg"]
        )

        def switch_to(provider, model_name, label_text):
            popup.dismiss()
            self.active_llm = provider.upper()
            self.model_btn.text = f"[ {provider.upper()[:6]} ]"
            self.add_bubble(f"Switching AI model to {label_text}...", is_user=True)
            
            def _worker():
                app = App.get_running_app()
                res = api_post("/llm/switch", {"provider": provider, "model": model_name}, token=app.token)
                if res.get("status") == "success":
                    msg = f"AI switched to {provider.upper()} ({model_name})! Knowledge Graph and chat will now use this model."
                    Clock.schedule_once(lambda dt: self.add_bubble(msg, is_user=False), 0)
                else:
                    err = res.get("detail", "Switch failed")
                    Clock.schedule_once(lambda dt: self.add_bubble(f"Switch error: {err}", is_user=False), 0)
            
            threading.Thread(target=_worker, daemon=True).start()

        for label_text, prov, mname in models:
            btn = Button(
                text=label_text,
                size_hint_y=None,
                height=dp(44),
                background_color=t["btn_primary"] if prov.upper() == self.active_llm else t["chip_bg"],
                background_normal="",
                color=(1, 1, 1, 1) if prov.upper() == self.active_llm else t["chip_fg"],
                font_size=sp(13),
                bold=True
            )
            btn.bind(on_press=lambda inst, p=prov, m=mname, l=label_text: switch_to(p, m, l))
            content.add_widget(btn)

        close_btn = Button(
            text="Close",
            size_hint_y=None,
            height=dp(40),
            background_color=t["btn_grey"],
            background_normal="",
            color=t["btn_grey_fg"],
            font_size=sp(13)
        )
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)

        popup.open()

    def _make_chip_handler(self, message: str):
        def handler(instance):
            self.text_input.text = message
            Clock.schedule_once(lambda dt: self.send_message(instance), 0.05)
        return handler

    def open_file_picker(self, instance):
        """Open Android storage-aware file picker."""
        dialog = DocumentPickerDialog(
            theme_name=self.theme_mode,
            on_file_selected=self.upload_file
        )
        dialog.show()

    def upload_file(self, filepath: str):
        filename = os.path.basename(filepath)
        self.add_bubble(f"Uploading '{filename}' into Knowledge Graph...", is_user=True)

        def _worker():
            app = App.get_running_app()
            res = api_upload_document(filepath, app.token)
            if "document" in res:
                data = res["document"]
                topics = data.get("topics_created", 1)
                title = data.get("title", filename)
                msg = f"'{title}' decomposed into {topics} topic notes & linked into your Knowledge Graph!"
                Clock.schedule_once(lambda dt: self.add_bubble(msg, is_user=False), 0)
            else:
                err = res.get("detail", "Upload failed")
                Clock.schedule_once(lambda dt: self.add_bubble(f"Upload failed: {err}", is_user=False), 0)

        threading.Thread(target=_worker, daemon=True).start()

    def on_enter_setup(self):
        app = App.get_running_app()
        self.header_title.text = f"Aurora — {app.username}"
        self.add_bubble("Hey! I'm Aurora. Connected to your personal Knowledge Graph.", is_user=False)
        
        # Query active LLM status from server
        def _fetch_active_llm():
            res = api_get("/llm/", token=app.token)
            if "current" in res:
                prov = res["current"].get("provider", "gemini").upper()
                self.active_llm = prov
                Clock.schedule_once(lambda dt: setattr(self.model_btn, "text", f"[ {prov[:6]} ]"), 0)
        
        threading.Thread(target=_fetch_active_llm, daemon=True).start()
        self._connect_ws()

    def _connect_ws(self):
        if not WS_AVAILABLE:
            self.add_bubble("Install websocket-client: pip install websocket-client", is_user=False)
            return
        app = App.get_running_app()
        url = f"{get_ws_base()}/chat?token={app.token}"
        self.status_dot.set_connecting()
        self.ws = WebSocketApp(
            url,
            on_open=self._ws_open,
            on_message=self._ws_message,
            on_error=self._ws_error,
            on_close=self._ws_close
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _ws_open(self, ws):
        Clock.schedule_once(lambda dt: self.status_dot.set_connected(), 0)

    def _ws_message(self, ws, raw):
        try:
            data = json.loads(raw)
            t = data.get("type")
            if t == "connected":
                Clock.schedule_once(lambda dt: self.add_bubble("Ready! What are your goals today?", is_user=False), 0)
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
        Clock.schedule_once(lambda dt: self.status_dot.set_disconnected(), 0)

    def _ws_close(self, ws, code, msg):
        Clock.schedule_once(lambda dt: self.status_dot.set_disconnected(), 0)

    def add_bubble(self, text: str, is_user: bool = False):
        bubble = ChatBubble(text=text, is_user=is_user, theme_name=self.theme_mode)
        self.chat_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def _show_thinking(self):
        self.thinking_bubble = ChatBubble(text="Aurora is thinking...", is_user=False, theme_name=self.theme_mode)
        self.chat_layout.add_widget(self.thinking_bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def _show_reply(self, reply: str):
        if self.thinking_bubble and self.thinking_bubble.parent:
            self.chat_layout.remove_widget(self.thinking_bubble)
            self.thinking_bubble = None
        self.add_bubble(reply, is_user=False)

    def send_message(self, instance):
        msg = self.text_input.text.strip()
        if not msg:
            return
        self.text_input.text = ""
        self.add_bubble(msg, is_user=True)
        if self.ws:
            try:
                self.ws.send(json.dumps({"message": msg, "session_id": SESSION_ID}))
            except Exception as e:
                self.add_bubble(f"Send failed: {e}", is_user=False)
        else:
            self.add_bubble("Not connected to backend.", is_user=False)
