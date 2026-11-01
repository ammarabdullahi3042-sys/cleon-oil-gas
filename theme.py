import customtkinter as ctk
from pathlib import Path
from tkinter import ttk


class Theme:
    """Editable professional dark theme for the station management app."""

    # Edit these palette values to experiment with the app's appearance.
    # Base surfaces
    BG = "#0B1018"                 # Main application background
    SIDEBAR = "#10182A"            # CLEON navy brand color
    SURFACE = "#141E2D"            # Panels and standard frames
    CARD = "#182436"               # KPI and content cards
    INPUT = "#0C1420"              # Entry fields and dropdowns
    BORDER = "#2A3749"             # Subtle outlines and separators

    # Text
    TEXT = "#F3F6FA"               # Main text
    TEXT_LIGHT = "#A8B5C7"         # Secondary text
    TEXT_MUTED = "#718096"         # Hints and less important labels

    # Brand and action colors
    BRAND_NAVY = "#10182A"
    BRAND_ORANGE = "#EC7624"
    PRIMARY = BRAND_NAVY
    SECONDARY = "#202C3E"
    ACCENT = BRAND_ORANGE
    ACCENT_HOVER = "#D56316"

    # Status colors
    SUCCESS = "#22C55E"
    WARNING = "#FBBF24"
    DANGER = "#F87171"
    INFO = "#38BDF8"

    # Product colors and dark row fills for tables
    PMS = "#60A5FA"                # PMS blue accent
    PMS_ROW = "#142A44"
    PMS_TEXT = "#BFDBFE"

    AGO = "#FBBF24"                # AGO amber/yellow accent
    AGO_ROW = "#382D16"
    AGO_TEXT = "#FDE68A"

    DPK = "#2DD4BF"
    LPG = "#A78BFA"

    # Layout
    SIDEBAR_WIDTH = 250
    CARD_RADIUS = 14
    BUTTON_RADIUS = 9
    PADDING = 14

    # Fonts
    TITLE_FONT = ("Segoe UI", 23, "bold")
    HEADING_FONT = ("Segoe UI", 16, "bold")
    SUBHEADING_FONT = ("Segoe UI", 14, "bold")
    BODY_FONT = ("Segoe UI", 12)
    BODY_BOLD_FONT = ("Segoe UI", 12, "bold")
    SMALL_FONT = ("Segoe UI", 10)

    @staticmethod
    def setup(mode=None):
        """Set the selected CLEON palette and table styles."""
        display_scale = 1.0
        if mode is None:
            try:
                from app_settings import get_display_scale, get_theme_mode
                mode = get_theme_mode()
                display_scale = get_display_scale()
            except Exception:
                mode = "dark"
        mode = "light" if str(mode).lower() == "light" else "dark"
        if mode == "light":
            Theme.BG = "#F3F6FA"
            Theme.SIDEBAR = "#10182A"
            Theme.SURFACE = "#FFFFFF"
            Theme.CARD = "#FFFFFF"
            Theme.INPUT = "#FFFFFF"
            Theme.BORDER = "#CBD5E1"
            Theme.TEXT = "#17202C"
            Theme.TEXT_LIGHT = "#475569"
            Theme.TEXT_MUTED = "#64748B"
            Theme.SECONDARY = "#E2E8F0"
        else:
            Theme.BG = "#0B1018"
            Theme.SIDEBAR = "#10182A"
            Theme.SURFACE = "#141E2D"
            Theme.CARD = "#182436"
            Theme.INPUT = "#0C1420"
            Theme.BORDER = "#2A3749"
            Theme.TEXT = "#F3F6FA"
            Theme.TEXT_LIGHT = "#A8B5C7"
            Theme.TEXT_MUTED = "#718096"
            Theme.SECONDARY = "#202C3E"
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme(str(Path(__file__).with_name("cleon_theme.json")))
        Theme.apply_display_scale(display_scale)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Treeview",
            background=Theme.SURFACE,
            foreground=Theme.TEXT,
            fieldbackground=Theme.SURFACE,
            bordercolor=Theme.BORDER,
            lightcolor=Theme.BORDER,
            darkcolor=Theme.BORDER,
            rowheight=round(24 * display_scale),
            font=("Segoe UI", max(8, round(9 * display_scale))),
        )
        style.configure(
            "Treeview.Heading",
            background=Theme.SECONDARY,
            foreground=Theme.TEXT,
            bordercolor=Theme.BORDER,
            relief="flat",
            anchor="center",
            font=("Segoe UI", max(8, round(9 * display_scale)), "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", Theme.ACCENT)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", Theme.PRIMARY)],
            foreground=[("active", Theme.TEXT)],
        )

    @staticmethod
    def apply_display_scale(scale):
        """Scale CustomTkinter controls and fonts together to preserve layout."""
        ctk.set_widget_scaling(0.92 * scale)
        style = ttk.Style()
        style.configure(
            "Treeview",
            rowheight=round(24 * scale),
            font=("Segoe UI", max(8, round(9 * scale))),
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", max(8, round(9 * scale)), "bold"),
        )

    @staticmethod
    def primary_button(master, text, command=None, **kwargs):
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            text_color="#FFFFFF",
            corner_radius=Theme.BUTTON_RADIUS,
            font=Theme.BODY_BOLD_FONT,
            **kwargs
        )

    @staticmethod
    def secondary_button(master, text, command=None, **kwargs):
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            fg_color=Theme.SECONDARY,
            hover_color=Theme.PRIMARY,
            text_color=Theme.TEXT,
            border_width=1,
            border_color=Theme.BORDER,
            corner_radius=Theme.BUTTON_RADIUS,
            font=Theme.BODY_BOLD_FONT,
            **kwargs
        )

    @staticmethod
    def danger_button(master, text, command=None, **kwargs):
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            text_color="#FEE2E2",
            corner_radius=Theme.BUTTON_RADIUS,
            font=Theme.BODY_BOLD_FONT,
            **kwargs
        )

    @staticmethod
    def card(master, **kwargs):
        return ctk.CTkFrame(
            master,
            fg_color=Theme.CARD,
            corner_radius=Theme.CARD_RADIUS,
            border_width=1,
            border_color=Theme.BORDER,
            **kwargs
        )

    @staticmethod
    def brand_wordmark(master, *, size=24, tagline=True, background="transparent"):
        """Create a high-contrast CLEON wordmark for dark application surfaces."""
        frame = ctk.CTkFrame(master, fg_color=background, corner_radius=0)
        word = ctk.CTkFrame(frame, fg_color="transparent")
        word.pack(anchor="w")
        ctk.CTkLabel(
            word, text="CLE", font=("Segoe UI", size, "bold"),
            text_color=Theme.TEXT
        ).pack(side="left")
        ctk.CTkLabel(
            word, text="ON", font=("Segoe UI", size, "bold"),
            text_color=Theme.BRAND_ORANGE
        ).pack(side="left")
        if tagline:
            ctk.CTkLabel(
                frame, text="OIL & GAS", font=("Segoe UI", max(9, size // 3), "bold"),
                text_color=Theme.BRAND_ORANGE
            ).pack(anchor="w", padx=(2, 0), pady=(0, 2))
        return frame

    @staticmethod
    def product_row_colors(product):
        """Return row background and text colors for a product."""
        product = str(product).strip().upper()
        if product == "PMS":
            return Theme.PMS_ROW, Theme.PMS_TEXT
        if product == "AGO":
            return Theme.AGO_ROW, Theme.AGO_TEXT
        return Theme.SURFACE, Theme.TEXT
