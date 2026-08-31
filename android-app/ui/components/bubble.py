"""
ui/components/bubble.py — Stylized Chat Bubble Card with Visual Avatar & Rich Markdown Formatter
"""
import os
import re
from pathlib import Path
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from ui.theme import THEMES

APP_ROOT = Path(__file__).parent.parent.parent.resolve()


def render_markdown_for_kivy(text: str) -> str:
    """
    Parses LLM Markdown (headings, bold, lists, wikilinks, code blocks, priorities)
    into clean, formatted Kivy markup with styled symbols (◆, ★, ▲, ⚡, ✦, ✓, •).
    """
    if not text:
        return ""

    # Replace square brackets in content to prevent Kivy BBCode parse breaks
    text = text.replace("&", "&amp;").replace("[[", "(").replace("]]", ")")

    # Format priorities with high-contrast colored symbol tags
    text = re.sub(
        r'(?i)\b(?:priority:\s*urgent|priority\s*urgent|urgent priority)\b',
        r'▲ [color=ff6b6b][b]Urgent[/b][/color]',
        text
    )
    text = re.sub(
        r'(?i)\b(?:priority:\s*high|priority\s*high|high priority)\b',
        r'⚡ [color=ffd93d][b]High[/b][/color]',
        text
    )
    text = re.sub(
        r'(?i)\b(?:priority:\s*medium|priority\s*medium|medium priority)\b',
        r'✦ [color=6bcb77][b]Medium[/b][/color]',
        text
    )
    text = re.sub(
        r'(?i)\b(?:priority:\s*low|priority\s*low|low priority)\b',
        r'• [color=4d96ff][b]Low[/b][/color]',
        text
    )

    # Format goals and milestones
    text = re.sub(r'(?i)\bgoal:\s*', r'◆ [b]Goal:[/b] ', text)
    text = re.sub(r'(?i)\bstatus:\s*completed\b', r'✓ [color=6bcb77][b]Completed[/b][/color]', text)
    text = re.sub(r'(?i)\bstatus:\s*in\s*progress\b', r'▶ [color=4d96ff][b]In Progress[/b][/color]', text)

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


class ChatBubble(BoxLayout):
    """
    Custom Chat Card Widget:
      - Visual icon avatar for Aurora / User
      - Formatted message body with symbols & colors
      - Smooth rounded card background
    """

    def __init__(self, text: str, is_user: bool = False, theme_name: str = "aurora", **kwargs):
        super().__init__(orientation="vertical", spacing=dp(4), padding=[dp(14), dp(10)], **kwargs)
        self.is_user = is_user
        self.theme_name = theme_name
        self.size_hint_y = None

        t = THEMES.get(theme_name, THEMES["aurora"])
        bg_col = t["user_bubble_bg"] if is_user else t["ai_bubble_bg"]
        badge_text = "You" if is_user else "Aurora"
        badge_col = t["badge_user_fg"] if is_user else t["badge_ai_fg"]

        # Sender identity header with mini icon
        badge_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(18),
            pos_hint={"right": 1} if is_user else {"x": 0}
        )

        if not is_user:
            icon_file = APP_ROOT / "assets" / "icons" / "theme_aurora.png"
            if icon_file.exists():
                icon_img = Image(
                    source=str(icon_file),
                    size_hint=(None, None),
                    size=(dp(14), dp(14)),
                    pos_hint={"center_y": 0.5}
                )
                badge_row.add_widget(icon_img)

        self.badge_lbl = Label(
            text=badge_text,
            font_size=sp(11),
            bold=True,
            color=badge_col,
            size_hint_x=None,
            width=dp(50) if is_user else dp(60),
            halign="right" if is_user else "left",
            valign="middle",
            pos_hint={"center_y": 0.5}
        )
        self.badge_lbl.bind(size=self.badge_lbl.setter("text_size"))
        badge_row.add_widget(self.badge_lbl)
        self.add_widget(badge_row)

        # Message body
        formatted_text = text if is_user else render_markdown_for_kivy(text)
        self.body_lbl = Label(
            text=formatted_text,
            markup=True,
            font_size=sp(15),
            color=t["user_bubble_fg"] if is_user else t["ai_bubble_fg"],
            size_hint_y=None,
            halign="right" if is_user else "left",
            valign="middle"
        )
        self.body_lbl.text_size = (Window.width * 0.78, None)
        self.body_lbl.bind(texture_size=self._update_body_size)
        self.add_widget(self.body_lbl)

        with self.canvas.before:
            self.rect_color = Color(*bg_col)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])

        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_body_size(self, instance, size):
        self.body_lbl.height = size[1]
        self.height = self.body_lbl.height + dp(42)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
