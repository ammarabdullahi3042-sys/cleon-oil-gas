"""Application entry point."""

import sqlite3
from tkinter import messagebox

from database import initialize_database
from login_window import LoginWindow


def main():
    try:
        initialize_database()
    except (sqlite3.Error, OSError) as error:
        messagebox.showerror(
            "Database Error",
            f"Could not initialize the station database:\n{error}",
        )
        return

    app = LoginWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
