import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


def _get_database_url():
    """Railway puede entregar 'postgres://' pero SQLAlchemy 2.x requiere 'postgresql://'"""
    url = os.environ.get('DATABASE_URL')
    if url:
        return url.replace('postgres://', 'postgresql://', 1)
    return 'sqlite:///' + os.path.join(basedir, 'muebles.db')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

    # MercadoPago
    MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN', '')
    MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY', '')

    # URL base del sitio (para callbacks de MercadoPago en producción)
    BASE_URL = os.environ.get('RAILWAY_PUBLIC_DOMAIN', os.environ.get('BASE_URL', 'http://127.0.0.1:5000'))
