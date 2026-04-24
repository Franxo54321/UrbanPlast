import logging
import requests
from flask import current_app

log = logging.getLogger(__name__)


def is_email_configured(app=None):
    cfg = (app or current_app).config
    return bool(cfg.get('BREVO_API_KEY') or cfg.get('MAIL_USERNAME'))


def send_email(subject, recipients, html, reply_to=None, text=None, app=None):
    """Send via Brevo HTTP API (preferred) or Flask-Mail fallback."""
    _app = app or current_app._get_current_object()
    if isinstance(recipients, str):
        recipients = [recipients]

    brevo_key = _app.config.get('BREVO_API_KEY', '')
    if brevo_key:
        return _send_brevo(_app, brevo_key, subject, recipients, html, reply_to, text)

    if _app.config.get('MAIL_USERNAME'):
        return _send_flask_mail(_app, subject, recipients, html, reply_to, text)

    log.warning('No email provider configured (BREVO_API_KEY and MAIL_USERNAME both empty)')
    return False


def _send_brevo(app, api_key, subject, recipients, html, reply_to, text):
    sender = app.config.get('MAIL_DEFAULT_SENDER', 'noreply@urbanplast.com')
    sender_name, sender_email = 'UrbanPlast', sender
    if '<' in sender:
        parts = sender.split('<')
        sender_name = parts[0].strip()
        sender_email = parts[1].strip('> ')

    payload = {
        'sender': {'name': sender_name, 'email': sender_email},
        'to': [{'email': r} for r in recipients],
        'subject': subject,
        'htmlContent': html,
    }
    if text:
        payload['textContent'] = text
    if reply_to:
        payload['replyTo'] = {'email': reply_to}

    try:
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            json=payload,
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            timeout=15
        )
        if resp.status_code in (200, 201, 202):
            return True
        log.error(f'Brevo API {resp.status_code}: {resp.text}')
        return False
    except Exception as e:
        log.error(f'Brevo send error: {e}')
        return False


def _send_flask_mail(app, subject, recipients, html, reply_to, text):
    from app import mail
    from flask_mail import Message
    with app.app_context():
        try:
            msg = Message(subject=subject, recipients=recipients, html=html)
            if text:
                msg.body = text
            if reply_to:
                msg.reply_to = reply_to
            mail.send(msg)
            return True
        except Exception as e:
            log.error(f'Flask-Mail send error: {e}')
            return False
