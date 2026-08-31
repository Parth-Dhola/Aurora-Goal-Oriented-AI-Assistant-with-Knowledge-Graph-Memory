"""
ui/components/icon_button.py — Visual Image-Backed Icon Button for Kivy
"""
import os
from pathlib import Path
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp

APP_ROOT = Path(__file__).parent.parent.parent.resolve()


class IconButton(ButtonBehavior, BoxLayout):
    """
    Button with real PNG icon asset and text label.
    100% font-independent, renders pixel-perfect on macOS desktop and Android.
    """

    def __init__(
        self,
        icon_name: str = "",
        text: str = "",
        bg_color=(0.15, 0.20, 0.32, 1),
        fg_color=(1, 1, 1, 1),
        radius=8,
        icon_size=(18, 18),
        font_size=12,
        **kwargs
    ):
        super().__init__(orientation="horizontal", spacing=dp(6), padding=[dp(8), dp(4)], **kwargs)
        self._bg_col_val = bg_color
        self._fg_col_val = fg_color

        with self.canvas.before:
            self.rect_color = Color(*bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._update_rect, size=self._update_rect)

        # Visual Image Icon
        self.icon_widget = None
        if icon_name:
            icon_file = APP_ROOT / "assets" / "icons" / f"{icon_name}.png"
            if icon_file.exists():
                self.icon_widget = Image(
                    source=str(icon_file),
                    size_hint=(None, None),
                    size=(dp(icon_size[0]), dp(icon_size[1])),
                    pos_hint={"center_y": 0.5}
                )
                self.add_widget(self.icon_widget)

        # Label
        self.lbl_widget = None
        if text:
            self.lbl_widget = Label(
                text=text,
                color=fg_color,
                bold=True,
                font_size=sp(font_size),
                halign="center",
                valign="middle",
                pos_hint={"center_y": 0.5}
            )
            self.lbl_widget.bind(size=self.lbl_widget.setter("text_size"))
            self.add_widget(self.lbl_widget)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_colors(self, bg_color, fg_color):
        self._bg_col_val = bg_color
        self._fg_col_val = fg_color
        self.rect_color.rgba = bg_color
        if self.lbl_widget:
            self.lbl_widget.color = fg_color

    def set_icon(self, icon_name: str):
        icon_file = APP_ROOT / "assets" / "icons" / f"{icon_name}.png"
        if icon_file.exists() and self.icon_widget:
            self.icon_widget.source = str(icon_file)

    def set_text(self, text: str):
        if self.lbl_widget:
            self.lbl_widget.text = text

