"""
ui/screens/chat.py — Real-Time Chat, Dynamic LLM Switcher & Document Ingestion Screen for Aurora
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
from ui.components.icon_button import IconButton


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
        ("Weak Areas",     "What are my weakest areas that I should improve?"),
        ("Weekly Review",  "Give me a weekly review of what I've accomplished."),
    ]

    THEME_KEYS = ["aurora", "light", "slate"]
    THEME_ICONS = {"aurora": "theme_aurora", "light": "theme_sun", "slate": "theme_moon"}
    LLM_ICONS = {
        "gemini": "llm_gemini",
        "local": "llm_local",
        "openai": "llm_openai",
        "groq": "llm_groq",
        "anthropic": "llm_anthropic"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ws = None
        self.thinking_bubble = None
        self.theme_mode = CURRENT_THEME
        self.active_llm = "gemini"
        self.available_options = []
        t = THEMES[self.theme_mode]

        self.root_layout = BoxLayout(orientation="vertical")

        # ── Header (Clean Icon-Only Controls) ─────────────────────────────────
        header = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            padding=[dp(12), dp(8)],
            spacing=dp(8)
        )

        # Left branding block: Status Dot + App Title
        left_block = BoxLayout(
            size_hint_x=0.60,
            spacing=dp(8),
            pos_hint={"center_y": 0.5}
        )
        self.status_dot = StatusDot(pos_hint={"center_y": 0.5})
        self.header_title = Label(
            text="Aurora",
            font_size=sp(18),
            bold=True,
            color=t["text_primary"],
            halign="left",
            valign="middle",
            pos_hint={"center_y": 0.5}
        )
        self.header_title.bind(size=self.header_title.setter("text_size"))
        left_block.add_widget(self.status_dot)
        left_block.add_widget(self.header_title)

        # Right control block: MCP Status + Model Switcher + Theme Toggle + Logout
        self.mcp_btn = IconButton(
            icon_name="mcp",
            text="",
            bg_color=(0.10, 0.35, 0.24, 1),
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_y": 0.5},
            radius=10
        )
        self.mcp_btn.bind(on_press=self.open_mcp_info)

        self.model_btn = IconButton(
            icon_name="llm_gemini",
            text="",
            bg_color=t["btn_grey"],
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_y": 0.5},
            radius=10
        )
        self.model_btn.bind(on_press=self.open_model_picker)

        self.theme_btn = IconButton(
            icon_name=self.THEME_ICONS.get(self.theme_mode, "theme_aurora"),
            text="",
            bg_color=t["btn_grey"],
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_y": 0.5},
            radius=10
        )
        self.theme_btn.bind(on_press=self.cycle_theme)

        self.logout_btn = IconButton(
            icon_name="logout",
            text="",
            bg_color=t["btn_grey"],
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_y": 0.5},
            radius=10
        )
        self.logout_btn.bind(on_press=self.logout)

        header.add_widget(left_block)
        header.add_widget(self.mcp_btn)
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
        
        self.attach_btn = IconButton(
            icon_name="doc",
            text="ATTACH",
            bg_color=t["btn_grey"],
            fg_color=t["btn_grey_fg"],
            size_hint=(None, None),
            size=(dp(96), dp(48)),
            pos_hint={"center_y": 0.5}
        )
        self.attach_btn.bind(on_press=self.open_file_picker)

        self.text_input = TextInput(
            hint_text="Message Aurora...",
            multiline=False,
            font_size=sp(16),
            size_hint_x=0.64,
            background_color=t["input_bg"],
            foreground_color=t["input_fg"],
            padding=[dp(14), dp(14)]
        )
        self.text_input.bind(on_text_validate=self.send_message)

        self.send_btn = IconButton(
            icon_name="send",
            text="SEND",
            bg_color=t["btn_primary"],
            fg_color=t.get("btn_primary_fg", (1, 1, 1, 1)),
            size_hint=(None, None),
            size=(dp(92), dp(48)),
            pos_hint={"center_y": 0.5}
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
        if getattr(self, "poll_timer", None):
            self.poll_timer.cancel()
            self.poll_timer = None
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
        self.theme_btn.set_icon(self.THEME_ICONS.get(self.theme_mode, "theme_aurora"))
        self.theme_btn.set_colors(t["btn_grey"])

        self._update_mcp_btn(getattr(self, "mcp_online", False))
        self.model_btn.set_colors(t["btn_grey"])
        self.logout_btn.set_colors(t["btn_grey"])

        self.attach_btn.set_colors(t["btn_grey"], t["btn_grey_fg"])
        self.text_input.background_color = t["input_bg"]
        self.text_input.foreground_color = t["input_fg"]
        self.send_btn.set_colors(t["btn_primary"], t.get("btn_primary_fg", (1, 1, 1, 1)))

        for chip in self.chip_buttons:
            chip.background_color = t["chip_bg"]
            chip.color = t["chip_fg"]

    def open_model_picker(self, instance):
        """Open popup displaying ONLY available/configured LLM options."""
        t = THEMES[self.theme_mode]
        app = App.get_running_app()

        # Retrieve fresh options from server
        try:
            res = api_get("/llm/", token=app.token)
            if "options" in res:
                self.available_options = res.get("options", [])
            if "current" in res:
                self.active_llm = res["current"].get("provider", "gemini").lower()
        except Exception:
            pass

        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))

        title = Label(
            text="Select AI Provider",
            font_size=sp(16),
            bold=True,
            size_hint_y=None,
            height=dp(28),
            color=t["text_primary"]
        )
        content.add_widget(title)

        body_container = BoxLayout(orientation="vertical", spacing=dp(8), size_hint=(1, 1))
        content.add_widget(body_container)

        popup = Popup(
            title="AI Brain Selection",
            content=content,
            size_hint=(0.94, 0.70),
            background_color=t["header_bg"]
        )

        def switch_to(provider, model_name, label_text):
            popup.dismiss()
            self.active_llm = provider.lower()
            self.active_model = model_name
            self.model_btn.set_icon(self.LLM_ICONS.get(self.active_llm, "llm_gemini"))
            self.add_bubble(f"Switching AI model to {label_text}...", is_user=True)
            
            def _worker():
                res = api_post("/llm/switch", {"provider": provider, "model": model_name}, token=app.token)
                if res.get("status") == "success":
                    msg = f"AI switched to {provider.upper()} ({model_name})! Knowledge Graph and chat will now use this model."
                    Clock.schedule_once(lambda dt: self.add_bubble(msg, is_user=False), 0)
                else:
                    err = res.get("detail", "Switch failed")
                    Clock.schedule_once(lambda dt: self.add_bubble(f"Switch error: {err}", is_user=False), 0)
            
            threading.Thread(target=_worker, daemon=True).start()

        def render_providers():
            body_container.clear_widgets()
            title.text = "Select AI Provider"

            scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
            prov_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
            prov_box.bind(minimum_height=prov_box.setter('height'))

            configured_opts = [opt for opt in self.available_options if opt.get("configured")]
            if not configured_opts:
                configured_opts = [{"id": "gemini", "name": "Google Gemini", "default_model": "gemini-3.1-flash-lite", "models": ["gemini-3.1-flash-lite"]}]

            for opt in configured_opts:
                prov = opt.get("id")
                pname = opt.get("name", prov.capitalize())
                models = opt.get("models") or [opt.get("default_model")]
                is_active_prov = (prov.lower() == self.active_llm.lower())

                status_suffix = f"  [Active: {getattr(self, 'active_model', opt.get('default_model'))}]" if is_active_prov else ""
                btn_text = f"{pname}  ({len(models)} models){status_suffix}"

                btn = Button(
                    text=btn_text,
                    size_hint_y=None,
                    height=dp(46),
                    background_color=t["btn_primary"] if is_active_prov else t["chip_bg"],
                    background_normal="",
                    color=(1, 1, 1, 1) if is_active_prov else t["chip_fg"],
                    font_size=sp(13),
                    bold=True
                )
                btn.bind(on_press=lambda inst, o=opt: render_models_for(o))
                prov_box.add_widget(btn)

            scroll.add_widget(prov_box)
            body_container.add_widget(scroll)

            close_btn = Button(
                text="Close",
                size_hint_y=None,
                height=dp(38),
                background_color=t["btn_grey"],
                background_normal="",
                color=t["btn_grey_fg"],
                font_size=sp(13)
            )
            close_btn.bind(on_press=popup.dismiss)
            body_container.add_widget(close_btn)

        def render_models_for(provider_opt):
            body_container.clear_widgets()
            prov = provider_opt.get("id")
            pname = provider_opt.get("name", prov.capitalize())
            title.text = f"{pname} Models"

            # Top navigation bar with Back button
            back_btn = Button(
                text="« Back to Providers",
                size_hint_y=None,
                height=dp(36),
                background_color=t["btn_grey"],
                background_normal="",
                color=t["btn_grey_fg"],
                font_size=sp(12),
                bold=True
            )
            back_btn.bind(on_press=lambda inst: render_providers())
            body_container.add_widget(back_btn)

            scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
            model_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
            model_box.bind(minimum_height=model_box.setter('height'))

            models = provider_opt.get("models") or [provider_opt.get("default_model")]
            current_active_model = getattr(self, "active_model", "")

            for mname in models:
                is_active = (prov.lower() == self.active_llm.lower() and (current_active_model == mname or not current_active_model and mname == provider_opt.get("default_model")))
                label_text = f"{mname}  {'[✓ Active]' if is_active else ''}"

                btn = Button(
                    text=label_text,
                    size_hint_y=None,
                    height=dp(42),
                    background_color=t["btn_primary"] if is_active else t["chip_bg"],
                    background_normal="",
                    color=(1, 1, 1, 1) if is_active else t["chip_fg"],
                    font_size=sp(12),
                    bold=True
                )
                btn.bind(on_press=lambda inst, p=prov, m=mname, l=f"{pname} ({mname})": switch_to(p, m, l))
                model_box.add_widget(btn)

            scroll.add_widget(model_box)
            body_container.add_widget(scroll)

        render_providers()
        popup.open()

    def open_mcp_info(self, *args):
        """Open Apollo MCP Server status and capabilities dialog."""
        t = THEMES[self.theme_mode]
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(14))

        status_text = "[color=38ef7d]Online & Active[/color]" if getattr(self, "mcp_online", False) else "[color=e67e22]Offline (DDG Fallback)[/color]"

        lbl = Label(
            text=(
                f"[b]Apollo Anti-Poison & Anti-Hallucination (MCP)[/b]\n\n"
                f"• [b]Status:[/b] {status_text}\n"
                f"• [b]Guardrails:[/b] Anti-Poison & Anti-Hallucination\n"
                f"• [b]Reranker:[/b] FlashRank CPU (<25ms)\n"
                f"• [b]Sources:[/b] arXiv, Semantic Scholar, GitHub, DuckDuckGo\n"
                f"• [b]Protocol:[/b] Standalone FastMCP 1.0\n"
            ),
            markup=True,
            font_size=sp(13),
            color=t["text_primary"],
            halign="left",
            valign="top"
        )
        lbl.bind(size=lbl.setter("text_size"))
        content.add_widget(lbl)

        popup = Popup(
            title="MCP Server Status",
            content=content,
            size_hint=(0.92, 0.52),
            background_color=t["header_bg"]
        )

        close_btn = Button(
            text="Close",
            size_hint_y=None,
            height=dp(40),
            background_color=t["btn_primary"],
            background_normal="",
            color=(1, 1, 1, 1),
            font_size=sp(13),
            bold=True
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
        
        # Query active LLM status and available options from server
        def _fetch_active_llm():
            res = api_get("/llm/", token=app.token)
            if "current" in res:
                prov = res["current"].get("provider", "gemini").lower()
                self.active_llm = prov
                self.available_options = res.get("options", [])
                icon_name = self.LLM_ICONS.get(prov, "llm_gemini")
                Clock.schedule_once(lambda dt: self._update_model_btn(icon_name), 0)

            mcp_data = res.get("mcp", {})
            self.mcp_online = mcp_data.get("online", False)
            Clock.schedule_once(lambda dt: self._update_mcp_btn(self.mcp_online), 0)
        
        threading.Thread(target=_fetch_active_llm, daemon=True).start()
        self.poll_timer = Clock.schedule_interval(self._poll_status, 10)
        self._connect_ws()

    def _update_model_btn(self, icon_name):
        self.model_btn.set_icon(icon_name)

    def _update_mcp_btn(self, online: bool):
        t = THEMES[self.theme_mode]
        if online:
            self.mcp_btn.set_colors((0.10, 0.38, 0.24, 1))
        else:
            self.mcp_btn.set_colors(t["btn_grey"])

    def _poll_status(self, dt=None):
        app = App.get_running_app()
        if not app or not app.token:
            return
        def _worker():
            res = api_get("/llm/", token=app.token)
            if "current" in res:
                prov = res["current"].get("provider", "gemini").lower()
                self.active_llm = prov
                self.available_options = res.get("options", [])
                icon_name = self.LLM_ICONS.get(prov, "llm_gemini")
                Clock.schedule_once(lambda dt: self._update_model_btn(icon_name), 0)

            mcp_data = res.get("mcp", {})
            self.mcp_online = mcp_data.get("online", False)
            Clock.schedule_once(lambda dt: self._update_mcp_btn(self.mcp_online), 0)
        threading.Thread(target=_worker, daemon=True).start()

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
