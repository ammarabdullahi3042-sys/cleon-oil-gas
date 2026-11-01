"""Login screen for the CLEON station application."""

import sqlite3
from tkinter import messagebox

import customtkinter as ctk

from app_settings import get_active_database, get_active_station_name
from dashboard import Dashboard
from theme import Theme


DATABASE = get_active_database()


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        Theme.setup()
        self.title(f"CLEON ERP Login | {get_active_station_name()}")
        self.geometry("420x390")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG)

        panel = ctk.CTkFrame(
            self, fg_color=Theme.CARD, corner_radius=16,
            border_width=1, border_color=Theme.BORDER
        )
        panel.pack(fill="both", expand=True, padx=28, pady=28)

        ctk.CTkLabel(
            panel, text="CLEON ERP", font=("Segoe UI", 25, "bold"),
            text_color=Theme.TEXT
        ).pack(pady=(28, 4))
        ctk.CTkLabel(
            panel, text="Station operations and accounts",
            font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT
        ).pack(pady=(0, 18))

        self.username = ctk.CTkEntry(
            panel, width=300, height=42, placeholder_text="Username"
        )
        self.username.pack(pady=8)
        self.password = ctk.CTkEntry(
            panel, width=300, height=42, placeholder_text="Password", show="*"
        )
        self.password.pack(pady=8)
        self.password.bind("<Return>", self.login)

        ctk.CTkButton(
            panel, text="Sign in", width=300, height=42,
            fg_color=Theme.ACCENT, hover_color=Theme.ACCENT_HOVER,
            font=Theme.BODY_BOLD_FONT, command=self.login
        ).pack(pady=(18, 12))

        self.username.focus_set()

    def login(self, event=None):
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            messagebox.showwarning(
                "Missing Details", "Enter your username and password.", parent=self
            )
            return

        try:
            with sqlite3.connect(get_active_database(), timeout=10) as conn:
                user = conn.execute(
                    "SELECT id, username, role FROM users "
                    "WHERE username=? AND password=?",
                    (username, password),
                ).fetchone()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error", f"Could not verify login:\n{error}", parent=self
            )
            return

        if not user:
            messagebox.showerror(
                "Login Failed", "The username or password is incorrect.", parent=self
            )
            self.password.delete(0, "end")
            self.password.focus_set()
            return

        # Close the login root, then launch the dashboard as the application's
        # main window. The database stores plain-text passwords in this version.
        self.destroy()
        app = Dashboard(login_username=username)
        app.mainloop()


if __name__ == "__main__":
    from database import initialize_database

    initialize_database(DATABASE)
    LoginWindow().mainloop()
