"""Editable dropdown that filters known values as the user types."""

import customtkinter as ctk


class SuggestionEntry(ctk.CTkComboBox):
    def __init__(self, master, values_provider, command=None, **kwargs):
        self._placeholder = kwargs.pop("placeholder_text", "")
        self._values_provider = values_provider
        self._selection_command = command
        self._showing_placeholder = False
        super().__init__(
            master, values=[], state="normal",
            command=self._on_selected, **kwargs
        )
        self._entry.delete(0, "end")
        self.bind("<KeyRelease>", self._update_suggestions, add="+")
        self.bind("<FocusIn>", self._clear_placeholder, add="+")
        self.bind("<FocusOut>", self._restore_placeholder, add="+")
        self._restore_placeholder()

    def get(self):
        if self._showing_placeholder:
            return ""
        return super().get()

    def insert(self, index, value):
        self._showing_placeholder = False
        self._entry.insert(index, value)

    def delete(self, first, last=None):
        self._showing_placeholder = False
        if last is None:
            self._entry.delete(first)
        else:
            self._entry.delete(first, last)

    def _clear_placeholder(self, _event=None):
        if self._showing_placeholder:
            self._entry.delete(0, "end")
            self._showing_placeholder = False

    def _update_suggestions(self, event):
        if self._showing_placeholder:
            return
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape"):
            return
        query = super().get().strip().casefold()
        if not query:
            self.configure(values=[])
            return
        matches = [
            value for value in self._values_provider()
            if str(value).casefold().startswith(query)
        ]
        self.configure(values=matches)
        if matches:
            self.after_idle(self._open_dropdown_menu)

    def _restore_placeholder(self, _event=None):
        if self._placeholder and not super().get().strip():
            super().set(self._placeholder)
            self._showing_placeholder = True

    def _on_selected(self, value):
        self._showing_placeholder = False
        if self._selection_command:
            self._selection_command(value)
