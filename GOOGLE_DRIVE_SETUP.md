# Google Drive backups for CLEON Version3

CLEON uploads a dated copy of the active station database only when you choose **Upload Backup**. Restoring from Drive replaces the current station database after making a local safety copy. Drive backups are stored in a folder named **CLEON ERP Backups**. The cloud snapshot redacts the legacy plain-text main-login password; restoring keeps the login credentials on the computer doing the restore.

## One-time setup

1. Install the optional Drive libraries from the Version3 PowerShell terminal:

   ```powershell
   cd C:\Users\ammar\FuelStationERP_V2\Version3
   python -m pip install -r requirements.txt
   ```

2. In [Google Cloud Console](https://console.cloud.google.com/), create or select a project and enable the **Google Drive API**.
3. Configure the OAuth consent screen for the Google account that will hold CLEON backups. If the app is in testing mode, add that Google account as a test user.
4. Create an OAuth client ID with application type **Desktop app**, then download its JSON file.
5. Open CLEON **Settings → Google Drive Backup → Connect Google Drive**, select the downloaded JSON, and finish Google's sign-in and consent flow in the browser.
6. Select **Upload Backup** when you want to save a station snapshot. To recover, select **Restore Latest**; CLEON asks for confirmation and saves a local safety copy first.

The OAuth client JSON and sign-in token are copied to the current Windows user's `%APPDATA%\CLEON ERP` folder. Keep the client JSON and token private. Disconnecting removes CLEON's local token; it does not delete Drive backups.

Each station uploads files with its station ID in the name. **Restore Latest** restores the newest Drive backup for the currently selected station only.
