"""
Run this ONCE, locally, on a machine where you can type the login code
Telegram sends you (and your 2FA password, if you have one set).

It logs in as your personal account and prints a session string.
Put that string in TG_SESSION_STRING (env var / secret) for main.py.

Never commit the printed session string anywhere. It is equivalent to
full access to your Telegram account.

Usage:
    pip install telethon
    python login.py
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

def main():
    api_id = int(input("API_ID (from https://my.telegram.org): ").strip())
    api_hash = input("API_HASH (from https://my.telegram.org): ").strip()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        # This will prompt for phone number, login code, and 2FA password
        # (if set) interactively — that's expected and only happens here.
        session_string = client.session.save()
        me = client.get_me()
        print(f"\nLogged in as: {me.first_name} (@{me.username or 'no-username'})")

        # Write to a file instead of relying on terminal copy-paste, since
        # terminal windows (especially Git Bash / MINGW64 on Windows) can
        # wrap or truncate long lines, causing an incomplete copy.
        with open("session_string.txt", "w", encoding="utf-8") as f:
            f.write(session_string)

        print("\nFull session string written to: session_string.txt")
        print("Open that file, select ALL the text (Ctrl+A), copy it (Ctrl+C),")
        print("and paste it as TG_SESSION_STRING in your .env file.")
        print("\nDo NOT share this string or commit it to source control.")
        print(f"\n(Length check: the string is {len(session_string)} characters long.")
        print(" If what you pasted into .env is shorter than that, it got cut off.)")

if __name__ == "__main__":
    main()