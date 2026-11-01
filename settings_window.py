"""Administrative settings, screen refresh, and safe data recovery controls."""

import sqlite3
import threading
from datetime import datetime
from tkinter import Canvas, filedialog, messagebox, simpledialog

import customtkinter as ctk

from app_settings import (
    change_access_password, change_login_credentials, create_station,
    get_active_station_id, get_active_station_name, get_active_database,
    get_display_scale, get_station_options, get_theme_mode,
    reset_operational_data, restore_last_backup, save_database_backup,
    save_display_scale, save_theme_mode, switch_active_station, verify_access,
)
from theme import Theme
from google_drive_backup import (
    connect_google_drive, disconnect_google_drive, google_drive_connected,
    restore_latest_station_backup, upload_station_backup,
)


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, dashboard):
        super().__init__(master)
        self.dashboard = dashboard
        self.station_restart_required = False
        self.display_scale = get_display_scale()
        Theme.setup()
        self.title("CLEON Application Settings")
        self.geometry("1240x760")
        self.minsize(1050, 650)
        self.configure(fg_color=Theme.BG)
        self.build_ui()
        self.transient(master)
        self.grab_set()

    def build_ui(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)
        ctk.CTkLabel(
            content, text="Application Settings", font=Theme.TITLE_FONT,
            text_color=Theme.TEXT
        ).pack(anchor="w", padx=20, pady=(12, 5))

        self.tabs = ctk.CTkTabview(
            content, fg_color=Theme.BG,
            segmented_button_fg_color=Theme.SURFACE,
            segmented_button_selected_color=Theme.ACCENT,
            segmented_button_selected_hover_color=Theme.ACCENT_HOVER,
            segmented_button_unselected_color=Theme.SURFACE,
        )
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(2, 12))
        self.tabs.add("Station & Appearance")
        self.tabs.add("Local Data")
        self.tabs.add("Google Drive")
        self.tabs.add("Passwords & Login")
        station_tab = self.tabs.tab("Station & Appearance")
        data_tab = self.tabs.tab("Local Data")
        drive_tab = self.tabs.tab("Google Drive")
        security_tab = self.tabs.tab("Passwords & Login")

        theme_card = Theme.card(station_tab)
        theme_card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(theme_card, text="Appearance", font=Theme.SUBHEADING_FONT,
                     text_color=Theme.TEXT).grid(row=0, column=0, sticky="w", padx=12, pady=10)
        self.theme_menu = ctk.CTkOptionMenu(
            theme_card, values=["Dark", "Light"], width=190
        )
        self.theme_menu.grid(row=0, column=1, padx=12, pady=10)
        self.theme_menu.set(get_theme_mode().title())
        Theme.primary_button(theme_card, "Save Theme", self.save_theme,
                             width=130).grid(row=0, column=2, padx=12, pady=10)
        self.display_icon = Canvas(
            theme_card, width=42, height=34, highlightthickness=0,
            bg=Theme.CARD
        )
        self.display_icon.grid(row=1, column=0, padx=(12, 2), pady=5, sticky="w")
        self.display_icon.create_rectangle(
            5, 3, 36, 23, outline=Theme.ACCENT, width=2
        )
        self.display_icon.create_line(20, 23, 20, 28, fill=Theme.ACCENT, width=2)
        self.display_icon.create_line(13, 29, 27, 29, fill=Theme.ACCENT, width=2)
        ctk.CTkLabel(
            theme_card, text="Display & Text Size",
            font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        controls = ctk.CTkFrame(theme_card, fg_color="transparent")
        controls.grid(row=1, column=2, padx=8, pady=5, sticky="e")
        Theme.secondary_button(
            controls, "A- Smaller",
            lambda: self.adjust_display_scale(-0.05), width=105
        ).pack(side="left", padx=3)
        self.display_scale_label = ctk.CTkLabel(
            controls, text=f"{self.display_scale:.0%}",
            font=Theme.BODY_BOLD_FONT, text_color=Theme.TEXT,
            width=48
        )
        self.display_scale_label.pack(side="left", padx=4)
        Theme.secondary_button(
            controls, "A+ Larger",
            lambda: self.adjust_display_scale(0.05), width=105
        ).pack(side="left", padx=3)
        Theme.secondary_button(
            controls, "Reset",
            lambda: self.set_display_scale(1.0), width=75
        ).pack(side="left", padx=3)
        ctk.CTkLabel(
            theme_card,
            text="Display size applies immediately and is saved for the next launch. Theme changes apply after reopening CLEON.",
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        station_card = Theme.card(station_tab)
        station_card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(station_card, text="Station Profiles",
                     font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).grid(
                         row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(station_card,
                     text="Each station keeps its own records. Switching stations applies after you close and reopen CLEON.",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
                      wraplength=1080, justify="left").grid(
                         row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 8))
        stations = get_station_options()
        self.station_labels = {
            f"{name}  [{station_id}]": station_id
            for station_id, name, _path in stations
        }
        self.station_menu = ctk.CTkOptionMenu(
            station_card, values=list(self.station_labels) or ["Main Station"], width=250)
        active_label = next((label for label, sid in self.station_labels.items()
                             if sid == get_active_station_id()), "Main Station  [main]")
        self.station_menu.set(active_label)
        self.station_menu.grid(row=2, column=0, padx=8, pady=8, sticky="w")
        Theme.secondary_button(station_card, "Switch Station", self.switch_station,
                               width=145).grid(row=2, column=1, padx=8, pady=8)
        self.new_station_entry = ctk.CTkEntry(
            station_card, placeholder_text="New station name", width=220)
        self.new_station_entry.grid(row=3, column=0, padx=8, pady=(0, 10), sticky="w")
        Theme.primary_button(station_card, "Create Station", self.add_station,
                             width=145).grid(row=3, column=1, padx=8, pady=(0, 10))
        self.active_station_label = ctk.CTkLabel(
            station_card, text=f"Current station: {get_active_station_name()}",
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_MUTED)
        self.active_station_label.grid(row=4, column=0, columnspan=3,
                                       sticky="w", padx=12, pady=(0, 10))

        refresh_card = Theme.card(data_tab)
        refresh_card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(refresh_card, text="Refresh saved information",
                     font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).pack(
                         anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(refresh_card,
                     text="Reload every open screen from the records in the database. This does not erase data.",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT).pack(
                         anchor="w", padx=12, pady=(0, 8))
        Theme.secondary_button(refresh_card, "Refresh All Screens",
                               self.refresh_all, width=190).pack(anchor="w", padx=12, pady=(0, 12))

        backup_card = Theme.card(data_tab)
        backup_card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(backup_card, text="Database Backup and Restore",
                     font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).pack(
                         anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(backup_card,
                     text="Save a point-in-time backup, or restore CLEON to the last saved backup. A safety copy is made before restore.",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
                      wraplength=1080, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        row = ctk.CTkFrame(backup_card, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 10))
        Theme.primary_button(row, "Save Backup", self.save_backup,
                             width=150).pack(side="left", padx=4)
        Theme.danger_button(row, "Restore Last Backup", self.restore_backup,
                            width=190).pack(side="left", padx=4)
        Theme.danger_button(row, "Reset Test Data", self.reset_test_data,
                            width=160).pack(side="left", padx=4)
        self.backup_path_label = ctk.CTkLabel(
            backup_card, text="Backup folder: backups\\fuel_station_latest_backup.db",
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_MUTED
        )
        self.backup_path_label.pack(anchor="w", padx=12, pady=(0, 10))
        ctk.CTkLabel(
            backup_card,
            text="Reset Test Data clears station setup and records for a fresh test, after making a dated backup. It keeps login credentials and theme settings.",
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
            wraplength=1080, justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        drive_card = Theme.card(drive_tab)
        drive_card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(drive_card, text="Google Drive Backup",
                     font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).pack(
                         anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(
            drive_card,
            text="Connect your Google account, then upload a dated backup on demand or restore the latest backup for this station. CLEON does not upload automatically.",
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
            wraplength=1080, justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 7))
        self.drive_status = ctk.CTkLabel(
            drive_card,
            text=("Google Drive connection saved" if google_drive_connected()
                  else "Google Drive is not connected"),
            font=Theme.SMALL_FONT,
            text_color=(Theme.SUCCESS if google_drive_connected() else Theme.TEXT_MUTED)
        )
        self.drive_status.pack(anchor="w", padx=12, pady=(0, 8))
        drive_actions = ctk.CTkFrame(drive_card, fg_color="transparent")
        drive_actions.pack(fill="x", padx=8, pady=(0, 10))
        Theme.secondary_button(drive_actions, "Connect Google Drive",
                               self.connect_drive, width=175).pack(side="left", padx=4)
        Theme.primary_button(drive_actions, "Upload Backup",
                             self.upload_drive_backup, width=145).pack(side="left", padx=4)
        Theme.secondary_button(drive_actions, "Restore Latest",
                               self.restore_drive_backup, width=145).pack(side="left", padx=4)
        Theme.danger_button(drive_actions, "Disconnect",
                            self.disconnect_drive, width=110).pack(side="left", padx=4)

        password_help = Theme.card(security_tab)
        password_help.pack(fill="x", padx=18, pady=(8, 2))
        ctk.CTkLabel(
            password_help, text="How to create or change an access password",
            font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT
        ).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            password_help,
            text=(
                "1. Choose the password type below: Accounts or Settings.\n"
                "2. Enter a new password of at least 10 characters in both boxes.\n"
                "3. Click Change, then enter the current Settings password when asked.\n"
                "4. To change the main app login, use the separate Main Login section below.\n"
                "5. The new password works immediately. Save it somewhere secure."
            ),
            font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
            justify="left", wraplength=1080
        ).pack(anchor="w", padx=12, pady=(0, 10))

        self._password_change_card(
            security_tab, "Change Accounts Access Password", "accounts", "account_password"
        ).pack(fill="x", padx=18, pady=8)
        self._password_change_card(
            security_tab, "Change Settings Access Password", "settings", "settings_password"
        ).pack(fill="x", padx=18, pady=8)

        self._login_change_card(security_tab).pack(fill="x", padx=18, pady=(8, 18))

    def _password_change_card(self, parent, title, access_key, entry_name):
        card = Theme.card(parent)
        ctk.CTkLabel(card, text=title, font=Theme.SUBHEADING_FONT,
                     text_color=Theme.TEXT).grid(row=0, column=0, sticky="w",
                                                 padx=12, pady=10)
        entry = ctk.CTkEntry(card, placeholder_text="New password (10+ characters)",
                             show="*", width=260)
        entry.grid(row=0, column=1, padx=8, pady=8)
        confirm = ctk.CTkEntry(card, placeholder_text="Confirm new password",
                               show="*", width=230)
        confirm.grid(row=0, column=2, padx=8, pady=8)
        Theme.secondary_button(
            card, "Change", lambda: self.change_password(
                access_key, entry, confirm
            ), width=90
        ).grid(row=0, column=3, padx=8, pady=8)
        for column in range(4):
            card.grid_columnconfigure(column, weight=column in (1, 2))
        setattr(self, entry_name, entry)
        return card

    def _login_change_card(self, parent):
        card = Theme.card(parent)
        ctk.CTkLabel(card, text="Change Main Login Username and Password",
                     font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).grid(
                         row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card,
                     text="This changes the login account currently signed in. The new details apply next time you sign in.",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
                     wraplength=1080, justify="left").grid(
                         row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        self.login_username_entry = ctk.CTkEntry(
            card, placeholder_text="New login username", width=220)
        self.login_username_entry.grid(row=2, column=0, padx=8, pady=8)
        if self.dashboard.login_username:
            self.login_username_entry.insert(0, self.dashboard.login_username)
        self.login_password_entry = ctk.CTkEntry(
            card, placeholder_text="New login password (10+ characters)",
            show="*", width=260)
        self.login_password_entry.grid(row=2, column=1, padx=8, pady=8)
        self.login_password_confirm = ctk.CTkEntry(
            card, placeholder_text="Confirm login password", show="*", width=220)
        self.login_password_confirm.grid(row=3, column=0, padx=8, pady=8)
        Theme.primary_button(card, "Update Main Login", self.change_login,
                             width=190).grid(row=3, column=1, padx=8, pady=8, sticky="w")
        return card

    def _confirm_settings_password(self):
        if self.station_restart_required:
            messagebox.showinfo(
                "Restart Required",
                "The active station selection has changed. Close and reopen CLEON before using Settings actions again.",
                parent=self,
            )
            return False
        password = simpledialog.askstring(
            "Settings Password", "Enter the Settings access password:",
            parent=self, show="*"
        )
        if password is None:
            return False
        if not verify_access("settings", password):
            messagebox.showerror(
                "Access Denied", "Settings password is incorrect.", parent=self)
            return False
        return True

    def save_theme(self):
        if self.station_restart_required:
            self._confirm_settings_password()
            return
        try:
            save_theme_mode(self.theme_menu.get().lower())
            messagebox.showinfo(
                "Theme Saved", "Theme preference saved. Close and reopen CLEON to apply it.",
                parent=self
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Theme Setting", str(error), parent=self)

    def adjust_display_scale(self, amount):
        self.set_display_scale(self.display_scale + amount)

    def set_display_scale(self, scale):
        scale = min(1.20, max(0.85, round(float(scale) * 20) / 20))
        try:
            save_display_scale(scale, get_active_database())
            self.display_scale = scale
            self.display_scale_label.configure(text=f"{scale:.0%}")
            Theme.apply_display_scale(scale)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Display & Text Size", str(error), parent=self)

    def switch_station(self):
        if not self._confirm_settings_password():
            return
        station_id = self.station_labels.get(self.station_menu.get())
        if not station_id:
            messagebox.showwarning("Select Station", "Select a station profile.", parent=self)
            return
        try:
            switch_active_station(station_id)
            self.station_restart_required = True
            self.active_station_label.configure(
                text=f"Active station after restart: {self.station_menu.get().split('  [')[0]}"
            )
            messagebox.showinfo(
                "Station Selected",
                "Close and reopen CLEON to load this station's separate database.",
                parent=self,
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Station", str(error), parent=self)

    def add_station(self):
        if not self._confirm_settings_password():
            return
        name = self.new_station_entry.get().strip()
        if not messagebox.askyesno(
            "Create Station",
            f"Create a new, separate station profile named '{name}'? It will start with empty station records and become active after restart.",
            parent=self,
        ):
            return
        try:
            station_id, database_path = create_station(name)
            self.station_restart_required = True
            self.new_station_entry.delete(0, "end")
            self.station_labels[f"{name}  [{station_id}]"] = station_id
            labels = list(self.station_labels)
            self.station_menu.configure(values=labels)
            new_label = next(label for label, sid in self.station_labels.items()
                             if sid == station_id)
            self.station_menu.set(new_label)
            self.active_station_label.configure(
                text=f"Active after restart: {name}"
            )
            messagebox.showinfo(
                "Station Created",
                f"'{name}' has a separate, empty database. Your current station data was not moved.\n\nDatabase: {database_path}\n\nClose and reopen CLEON to sign in to the new station.",
                parent=self,
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Create Station", str(error), parent=self)

    def refresh_all(self):
        if not self._confirm_settings_password():
            return
        self.dashboard.refresh_all_pages()
        messagebox.showinfo(
            "Refreshed", "Open screens reloaded from saved records.", parent=self)

    def save_backup(self):
        if not self._confirm_settings_password():
            return
        try:
            path = save_database_backup()
            self.backup_path_label.configure(text=f"Latest backup: {path}")
            messagebox.showinfo(
                "Backup Saved", f"Database backup saved to:\n{path}", parent=self)
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Backup Error", str(error), parent=self)

    def connect_drive(self):
        if not self._confirm_settings_password():
            return
        oauth_file = filedialog.askopenfilename(
            parent=self,
            title="Select Google OAuth Desktop Client JSON",
            filetypes=[("JSON files", "*.json")],
        )
        if not oauth_file:
            return
        self._run_drive_job(
            lambda: connect_google_drive(oauth_file),
            "Google Drive connected. CLEON can now upload and restore station backups.",
        )

    def upload_drive_backup(self):
        if not self._confirm_settings_password():
            return
        if not google_drive_connected():
            messagebox.showinfo("Connect Google Drive", "Connect your Google account first.", parent=self)
            return
        if not messagebox.askyesno(
            "Upload Station Backup",
            "Upload a dated snapshot of this station's database to the CLEON ERP Backups folder in your Google Drive?",
            parent=self,
        ):
            return
        self._run_drive_job(
            lambda: upload_station_backup(get_active_database()),
            "Station backup uploaded to Google Drive.",
        )

    def restore_drive_backup(self):
        if not self._confirm_settings_password():
            return
        if not google_drive_connected():
            messagebox.showinfo("Connect Google Drive", "Connect your Google account first.", parent=self)
            return
        if not messagebox.askyesno(
            "Restore From Google Drive",
            "Replace this station's current records with its newest Google Drive backup? A dated safety copy of the current database will be saved first.",
            parent=self,
        ):
            return
        self._run_drive_job(
            lambda: restore_latest_station_backup(get_active_database()),
            None,
            refresh=True,
        )

    def disconnect_drive(self):
        if not self._confirm_settings_password():
            return
        disconnect_google_drive()
        self.drive_status.configure(text="Google Drive is disconnected.", text_color=Theme.TEXT_MUTED)
        messagebox.showinfo(
            "Disconnected", "CLEON removed its saved Google sign-in. Existing Drive backups were not deleted.", parent=self)

    def _run_drive_job(self, action, success_text, refresh=False):
        self.drive_status.configure(text="Working with Google Drive…", text_color=Theme.INFO)

        def worker():
            try:
                result = action()
            except Exception as error:
                self.after(0, lambda error=error: self._drive_job_failed(error))
            else:
                self.after(0, lambda: self._drive_job_succeeded(
                    result, success_text, refresh
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _drive_job_failed(self, error):
        self.drive_status.configure(text="Google Drive action failed.", text_color=Theme.DANGER)
        messagebox.showerror("Google Drive", str(error), parent=self)

    def _drive_job_succeeded(self, result, success_text, refresh):
        self.drive_status.configure(text="Google Drive is connected.", text_color=Theme.SUCCESS)
        if isinstance(result, tuple) and len(result) == 2:
            backup_name, safety_path = result
            if refresh:
                self.dashboard.refresh_all_pages()
            messagebox.showinfo(
                "Drive Restore Complete",
                f"Restored backup: {backup_name}\n\nSafety copy of replaced records: {safety_path}",
                parent=self,
            )
        elif success_text:
            if refresh:
                self.dashboard.refresh_all_pages()
            messagebox.showinfo("Google Drive", success_text, parent=self)

    def restore_backup(self):
        if not self._confirm_settings_password():
            return
        if not messagebox.askyesno(
            "Restore Last Backup",
            "This replaces current station records with the last saved backup. "
            "A safety copy of current data will be made first. Continue?",
            parent=self,
        ):
            return
        try:
            safety = restore_last_backup()
            self.dashboard.refresh_all_pages()
            messagebox.showinfo(
                "Backup Restored",
                f"Records restored. A safety copy of the data replaced is at:\n{safety}",
                parent=self,
            )
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Restore Error", str(error), parent=self)

    def reset_test_data(self):
        if not self._confirm_settings_password():
            return
        confirmed = messagebox.askyesno(
            "Reset Test Data",
            "This permanently clears station setup and operating records in this Version3 database: tanks, pumps, attendants, dips, receipts, sessions, expenses, account transactions and selling prices.\n\n"
            "A dated safety backup will be created first. Login credentials, Settings passwords and theme are kept. Continue?",
            parent=self,
        )
        if not confirmed:
            return
        typed = simpledialog.askstring(
            "Confirm Full Reset", "Type RESET to clear the Version3 test data:",
            parent=self
        )
        if typed != "RESET":
            if typed is not None:
                messagebox.showinfo("Reset Cancelled", "You did not type RESET. No data was cleared.", parent=self)
            return
        try:
            backup = reset_operational_data()
            self.dashboard.refresh_all_pages()
            messagebox.showinfo(
                "Test Data Cleared",
                f"Version3 is ready for fresh setup. A full backup was saved at:\n{backup}",
                parent=self,
            )
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Reset Error", str(error), parent=self)

    def change_login(self):
        if not self._confirm_settings_password():
            return
        new_username = self.login_username_entry.get().strip()
        new_password = self.login_password_entry.get()
        if new_password != self.login_password_confirm.get():
            messagebox.showwarning("Password Mismatch", "The login passwords do not match.", parent=self)
            return
        try:
            old_username = self.dashboard.login_username
            if not old_username:
                with sqlite3.connect(get_active_database(), timeout=10) as conn:
                    row = conn.execute("SELECT username FROM users ORDER BY id LIMIT 1").fetchone()
                old_username = row[0] if row else None
            updated_username = change_login_credentials(old_username, new_username, new_password)
            self.dashboard.login_username = updated_username
            self.login_password_entry.delete(0, "end")
            self.login_password_confirm.delete(0, "end")
            messagebox.showinfo(
                "Login Updated", "Main login username and password updated. Use the new details next time you sign in.", parent=self)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showwarning("Login Not Updated", str(error), parent=self)

    def change_password(self, access_key, entry, confirm):
        if not self._confirm_settings_password():
            return
        new_password = entry.get()
        if new_password != confirm.get():
            messagebox.showwarning(
                "Password Mismatch", "The new passwords do not match.", parent=self)
            return
        try:
            change_access_password(access_key, new_password)
            entry.delete(0, "end")
            confirm.delete(0, "end")
            messagebox.showinfo(
                "Password Changed", "Access password updated successfully.", parent=self)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showwarning(
                "Password Not Changed", str(error), parent=self)
