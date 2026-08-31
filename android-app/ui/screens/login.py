"""
ui/screens/login.py — Login, Registration, and Server Configuration Screen
"""
import threading
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.metrics import dp, sp

from core.config import SERVER_URL, CURRENT_THEME, normalize_url, set_server_url
from core.api import api_post
from ui.theme import THEMES


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
        set_server_url(value)

    def toggle_show_password(self, instance):
        self.show_pwd = not self.show_pwd
        self.password_input.password = not self.show_pwd
        self.eye_btn.text = "HIDE" if self.show_pwd else "SHOW"

    def login(self, instance):
        threading.Thread(target=self._auth, args=("/auth/login",), daemon=True).start()

    def register(self, instance):
        threading.Thread(target=self._auth, args=("/auth/register",), daemon=True).start()

    def _auth(self, endpoint):
        target_url = normalize_url(self.server_input.text)
        set_server_url(target_url)
        username = self.username_input.text.strip()
        password = self.password_input.text.strip()
        if not username or not password:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", "Please enter username & password"), 0)
            return

        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"Connecting to {target_url}..."), 0)
        result = api_post(endpoint, {"username": username, "password": password})
        if "access_token" in result:
            app = App.get_running_app()
            app.token = result["access_token"]
            app.username = result["username"]
            Clock.schedule_once(lambda dt: self._go_to_chat(), 0)
        else:
            error = result.get("detail", result.get("error", "Authentication failed"))
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", error), 0)

    def _go_to_chat(self):
        chat = self.manager.get_screen("chat")
        chat.on_enter_setup()
        self.manager.current = "chat"
