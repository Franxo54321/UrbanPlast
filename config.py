import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


def _get_database_url():
    """Railway puede entregar 'postgres://' pero SQLAlchemy 2.x requiere 'postgresql://'"""
    url = os.environ.get('DATABASE_URL')
    if url:
        return url.replace('postgres://', 'postgresql://', 1)
    return 'sqlite:///' + os.path.join(basedir, 'muebles.db')


def _get_base_url():
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
    if railway_domain:
        if railway_domain.startswith('http://') or railway_domain.startswith('https://'):
            return railway_domain
        return f'https://{railway_domain}'

    base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000').strip()
    if base_url.startswith('http://') or base_url.startswith('https://'):
        return base_url
    return f'https://{base_url}'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # MercadoPago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN', '')
    MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY', '')
    MP_WEBHOOK_SECRET = os.environ.get('MP_WEBHOOK_SECRET', '')

    # Email (Flask-Mail)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@urbanplast.com')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@urbanplast.com')

    # URL base del sitio (para callbacks de MercadoPago y links de email en producción)
    BASE_URL = _get_base_url()
