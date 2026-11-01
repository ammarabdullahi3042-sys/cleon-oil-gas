"""Numeric entry widget with comma-grouped display values."""

import customtkinter as ctk


def _group_digits(value):
    if not value:
        return ""
    groups = []
    while value:
        groups.append(value[-3:])
        value = value[:-3]
    return ",".join(reversed(groups))


def format_number_text(value):
    """Add thousands separators while preserving partial decimal input."""
    raw = value.replace(",", "")
    sign = ""
    if raw.startswith("-"):
        sign, raw = "-", raw[1:]
    if raw.count(".") > 1 or any(
        character not in "0123456789." for character in raw
    ):
        return value
    integer, has_decimal, fraction = raw.partition(".")
    grouped = _group_digits(integer)
    return sign + grouped + ("." + fraction if has_decimal else "")


class FormattedNumberEntry(ctk.CTkEntry):
    """Entry that shows grouped digits but returns an ungrouped value."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind("<KeyRelease>", self._format_display, add="+")

    def get(self):
        return super().get().replace(",", "")

    def insert(self, index, string):
        super().insert(index, string)
        self._format_display()

    def _format_display(self, _event=None):
        value = super().get()
        formatted = format_number_text(value)
        if formatted == value:
            return

        cursor = self.index("insert")
        characters_before_cursor = len(value[:cursor].replace(",", ""))
        previous_state = self.cget("state")
        if previous_state == "disabled":
            self.configure(state="normal")
        self.delete(0, "end")
        super().insert(0, formatted)
        if previous_state == "disabled":
            self.configure(state="disabled")

        cursor_position = 0
        if characters_before_cursor:
            characters_seen = 0
            for position, character in enumerate(formatted, start=1):
                if character != ",":
                    characters_seen += 1
                cursor_position = position
                if characters_seen == characters_before_cursor:
                    break
        self.icursor(cursor_position)
