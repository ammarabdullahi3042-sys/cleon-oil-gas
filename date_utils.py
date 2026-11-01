"""Flexible date parsing and a small built-in calendar picker for CTkEntry fields."""
import calendar
from datetime import date, datetime
import customtkinter as ctk
from tkinter import Menu, messagebox

DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%m/%d/%Y", "%m-%d-%Y",
)


def parse_flexible_date(value):
    """Parse ISO, Nigerian day-first numeric, and common written date forms."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Enter a date.")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError("Use a date such as 30/09/2026, 30-09-2026, or 2026-09-30.")


def format_display_date(value):
    """Format valid ERP dates as DD-MM-YY, preserving unrecognized text."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    if " to " in raw:
        start, end = raw.split(" to ", 1)
        return f"{format_display_date(start)} to {format_display_date(end)}"
    try:
        return parse_flexible_date(raw).strftime("%d-%m-%y")
    except ValueError:
        return raw


def normalize_date_entry(entry, show_error=False):
    value = entry.get().strip()
    if not value:
        return None
    try:
        parsed = parse_flexible_date(value)
    except ValueError as error:
        if show_error:
            messagebox.showerror("Invalid Date", str(error), parent=entry.winfo_toplevel())
        return None
    entry.delete(0, "end")
    entry.insert(0, parsed.strftime("%d-%m-%y"))
    return parsed


def attach_date_picker(entry):
    """Normalize on blur; F4, Alt+Down, double-click or right-click opens a calendar."""
    normalize_date_entry(entry)
    entry.bind("<FocusOut>", lambda _event: normalize_date_entry(entry), add="+")
    entry.bind("<Double-Button-1>", lambda _event: (open_calendar(entry), "break"), add="+")
    entry.bind("<Control-Down>", lambda _event: (open_calendar(entry), "break"), add="+")
    entry.bind("<Alt-Down>", lambda _event: (open_calendar(entry), "break"), add="+")
    entry.bind("<F4>", lambda _event: (open_calendar(entry), "break"), add="+")
    menu = Menu(entry, tearoff=0)
    menu.add_command(label="Choose date…", command=lambda: open_calendar(entry))
    entry.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root), add="+")
    return entry


def open_calendar(entry):
    try:
        selected = parse_flexible_date(entry.get())
    except ValueError:
        selected = date.today()
    month = [selected.year, selected.month]
    popup = ctk.CTkToplevel(entry.winfo_toplevel())
    popup.title("Choose a date")
    popup.resizable(False, False)
    popup.transient(entry.winfo_toplevel())
    container = ctk.CTkFrame(popup, corner_radius=12)
    container.pack(fill="both", expand=True, padx=12, pady=12)
    header = ctk.CTkFrame(container, fg_color="transparent")
    header.pack(fill="x", pady=(2, 8))
    title = ctk.CTkLabel(header, text="", font=("Segoe UI", 15, "bold"))
    title.pack(side="left", expand=True)
    grid = ctk.CTkFrame(container, fg_color="transparent")
    grid.pack()

    def draw():
        for child in grid.winfo_children():
            child.destroy()
        title.configure(text=f"{calendar.month_name[month[1]]} {month[0]}")
        for col, label in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ctk.CTkLabel(grid, text=label, width=38, font=("Segoe UI", 11, "bold")).grid(row=0, column=col, padx=2, pady=3)
        for row, week in enumerate(calendar.monthcalendar(month[0], month[1]), start=1):
            for col, day in enumerate(week):
                if day:
                    ctk.CTkButton(grid, text=str(day), width=36, height=30,
                                  command=lambda d=day: choose(d)).grid(row=row, column=col, padx=2, pady=2)

    def shift(delta):
        month[1] += delta
        if month[1] < 1:
            month[0] -= 1; month[1] = 12
        elif month[1] > 12:
            month[0] += 1; month[1] = 1
        draw()

    def choose(day):
        entry.delete(0, "end")
        entry.insert(0, date(month[0], month[1], day).strftime("%d-%m-%y"))
        popup.destroy()
        entry.event_generate("<FocusOut>")

    ctk.CTkButton(header, text="‹", width=32, command=lambda: shift(-1)).pack(side="left")
    ctk.CTkButton(header, text="›", width=32, command=lambda: shift(1)).pack(side="right")
    draw()
    popup.update_idletasks()
    popup.update()
    width = popup.winfo_reqwidth()
    height = popup.winfo_reqheight()
    x = min(entry.winfo_rootx(), entry.winfo_screenwidth() - width - 8)
    y = entry.winfo_rooty() + entry.winfo_height() + 4
    if y + height > entry.winfo_screenheight():
        y = max(8, entry.winfo_rooty() - height - 4)
    popup.geometry(f"+{x}+{y}")
    popup.wait_visibility()
    popup.lift()
    popup.focus_force()
    popup.grab_set()
