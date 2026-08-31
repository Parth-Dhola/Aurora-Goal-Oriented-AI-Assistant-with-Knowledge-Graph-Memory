"""
ui/components/file_picker.py — Android Storage-Compatible Document Picker Dialog
"""
import os
from pathlib import Path
from typing import Callable, Optional

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.metrics import dp, sp
from ui.theme import THEMES


def get_android_default_paths() -> list:
    """Find valid Android storage paths, prioritizing user Download/Documents folders."""
    candidates = [
        "/storage/emulated/0/Download",
        "/storage/emulated/0/Documents",
        "/sdcard/Download",
        "/sdcard/Documents",
        "/storage/emulated/0",
        "/sdcard",
        str(Path.home() / "Downloads"),
        str(Path.home() / "Documents"),
        str(Path.home()),
    ]
    return [p for p in candidates if os.path.exists(p)]


class DocumentPickerDialog:
    """Popup for selecting and uploading PDF/TXT study notes into Knowledge Graph."""

    def __init__(self, theme_name: str, on_file_selected: Callable[[str], None]):
        self.theme_name = theme_name
        self.on_file_selected = on_file_selected
        self.popup = None

    def show(self):
        t = THEMES.get(self.theme_name, THEMES["aurora"])
        valid_paths = get_android_default_paths()
        initial_path = valid_paths[0] if valid_paths else str(Path.home())

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))

        # Quick Jump Directory Bar
        quick_bar = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        
        def jump_to(target_dir):
            if os.path.exists(target_dir):
                filechooser.path = target_dir

        for label, dir_path in [
            ("Downloads", "/storage/emulated/0/Download"),
            ("Documents", "/storage/emulated/0/Documents"),
            ("Storage", "/storage/emulated/0"),
            ("Home", str(Path.home()))
        ]:
            btn = Button(
                text=label,
                size_hint_x=0.25,
                background_color=t["chip_bg"],
                background_normal="",
                color=t["chip_fg"],
                font_size=sp(11),
                bold=True
            )
            target = dir_path if os.path.exists(dir_path) else str(Path.home())
            btn.bind(on_press=lambda inst, p=target: jump_to(p))
            quick_bar.add_widget(btn)

        content.add_widget(quick_bar)

        # File Chooser
        filechooser = FileChooserListView(
            path=initial_path,
            filters=["*.pdf", "*.txt", "*.PDF", "*.TXT"]
        )
        content.add_widget(filechooser)

        # Action Buttons
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

        self.popup = Popup(
            title="Select Study PDF or Notes",
            content=content,
            size_hint=(0.94, 0.88),
            background_color=t["header_bg"]
        )
        cancel_btn.bind(on_press=self.popup.dismiss)

        def do_upload(btn_instance):
            selected = filechooser.selection
            if not selected:
                return
            self.popup.dismiss()
            filepath = selected[0]
            self.on_file_selected(filepath)

        upload_btn.bind(on_press=do_upload)
        btn_bar.add_widget(cancel_btn)
        btn_bar.add_widget(upload_btn)
        content.add_widget(btn_bar)

        self.popup.open()

