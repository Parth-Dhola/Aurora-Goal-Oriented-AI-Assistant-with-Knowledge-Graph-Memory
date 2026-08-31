"""
Aurora Android Mobile Application — Main Entry Point

A Goal-Oriented AI Productivity Assistant with SQLite Knowledge Graph Memory.
Features:
  - Real-time WebSocket chat
  - Multi-theme engine (Aurora Glow, Warm Paper, Soft Slate)
  - Android storage-aware PDF & notes uploader
  - Dynamic soft-keyboard avoidance
  - Auto-normalizing server URL configuration
"""
import sys
from pathlib import Path

# Add android-app folder to Python module path
APP_ROOT = Path(__file__).parent.resolve()
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

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
