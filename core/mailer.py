"""Отправка email (SMTP)."""
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# =====================================================
# EMAIL
# =====================================================

MAIL_FROM     = os.getenv("MAIL_FROM", "citypause@mail.ru")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")

def send_email(to, subject, html_body, attachments=None):
    """
    attachments: список словарей. Поддерживаются два варианта:
      - {"filename": "dogovor_123.txt", "content": "...текст..."} — текстовое вложение (UTF-8)
      - {"filename": "dogovor_123.pdf", "filepath": "/data/contracts/GP-XXXXXX.pdf"} — бинарный файл с диска (PDF и т.п.)
    """
    if not MAIL_PASSWORD:
        print("WARNING: MAIL_PASSWORD not set")
        return
    try:
        from email.header import Header
        from email.utils import formataddr
        msg = MIMEMultipart("mixed")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"]    = formataddr((str(Header("Gorodskaya Pauza", "utf-8")), MAIL_FROM))
        msg["To"]      = to
        msg["MIME-Version"] = "1.0"

        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_part)

        for att in (attachments or []):
            filename = att.get("filename", "attachment.txt")
            if "filepath" in att:
                with open(att["filepath"], "rb") as f:
                    payload_bytes = f.read()
            else:
                payload_bytes = att.get("content", "").encode("utf-8")
            part = MIMEBase("application", "octet-stream")
            part.set_payload(payload_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.mail.ru", 465) as server:
            server.login(MAIL_FROM, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, [to], msg.as_string())
        print("OK EMAIL sent to " + to)
    except Exception as e:
        print("ERROR email: " + str(e))
