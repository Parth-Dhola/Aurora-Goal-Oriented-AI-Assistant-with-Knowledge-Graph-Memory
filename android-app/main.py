"""
Aurora Android Mobile Application — Main Entry Point

A Goal-Oriented AI Productivity Assistant with SQLite Knowledge Graph Memory.
Features:
  - Full Unicode & Emoji font support
  - Real-time WebSocket chat
  - Multi-theme engine (Aurora Glow, Warm Paper, Soft Slate)
  - Android storage-aware PDF & notes uploader
  - Dynamic soft-keyboard avoidance
  - Auto-normalizing server URL configuration
"""
import os
import sys
from pathlib import Path

# Add android-app folder to Python module path
APP_ROOT = Path(__file__).parent.resolve()
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Register Unicode Font to support all emojis, icons, and mathematical symbols
from kivy.core.text import LabelBase

font_candidates = [
    str(APP_ROOT / "fonts" / "UnicodeFont.ttf"),
    str(APP_ROOT / "fonts" / "DejaVuSans.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
selected_font = None
for fpath in font_candidates:
    if os.path.exists(fpath):
        selected_font = fpath
        break

if selected_font:
    try:
        LabelBase.register(
            name="Roboto", # Overrides Kivy default font so all labels inherit full emoji/symbol support
            fn_regular=selected_font,
            fn_bold=selected_font,
            fn_italic=selected_font,
            fn_bolditalic=selected_font
        )
    except Exception as e:
        print(f"[Font] Register warning: {e}")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.core.window import Window

from core.config import CURRENT_THEME
from ui.theme import THEMES
from ui.screens.login import LoginScreen
from ui.screens.chat import ChatScreen

# Set initial window background color and soft keyboard behavior
Window.clearcolor = THEMES.get(CURRENT_THEME, THEMES["aurora"])["window_bg"]
Window.softinput_mode = "below_target"


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
