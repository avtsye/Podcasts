import os
import smtplib
from email.message import EmailMessage

def send_notification(podcast, episode, drive_file):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["MAIL_TO"]
    sender = os.getenv("MAIL_FROM", username)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f'{os.getenv("MAIL_SUBJECT_PREFIX", "[Podcasts]")} {podcast["name"]} — {episode["title"]}'
    msg.set_content(
        f'פודקאסט חדש עלה.\n\nפודקאסט: {podcast["name"]}\n'
        f'פרק: {episode["title"]}\nתאריך: {episode.get("published", "")}\n'
        f'קישור ל-Google Drive: {drive_file.get("webViewLink", "")}\n'
    )

    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)
