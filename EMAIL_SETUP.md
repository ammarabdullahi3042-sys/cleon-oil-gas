# Product-finished report email

The desktop app sends the Product / Delivery PDF after a product run is finished. The sender and recipient are the addresses saved under **Reports Centre → Product-finished report email**.

Gmail SMTP defaults are built in:

- Server: `smtp.gmail.com`
- Port: `587`
- Security: STARTTLS
- Username: the configured sender address (or `CLEON_SMTP_USERNAME`)
- Password: a Google App Password for that sender account

Google requires 2-Step Verification before an App Password can be created. Sign in to the sender's Google account, open [Google Account App Passwords](https://myaccount.google.com/apppasswords), create an app password, then set it as `CLEON_SMTP_PASSWORD` in the environment used to launch the desktop app. Do not put the App Password in source code or commit it.

If the sender is an alias, Gmail must already be authorized to send as that address. For another mail provider, set `CLEON_SMTP_HOST`, `CLEON_SMTP_PORT`, and any required username/password environment variables.
