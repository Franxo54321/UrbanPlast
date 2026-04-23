import os
import secrets
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["500 per day"])

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Iniciá sesión para continuar.'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from app.main.routes import main_bp
    from app.auth.routes import auth_bp
    from app.admin.routes import admin_bp
    from app.cart.routes import cart_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(cart_bp, url_prefix='/cart')

    # Excluir webhook de MercadoPago de CSRF
    csrf.exempt('app.cart.routes.mp_webhook')

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_categories():
        from app.models import Category
        return dict(categories=Category.query.all())

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    with app.app_context():
        db.create_all()
        _create_default_admin(app)
        _create_default_categories()
        _create_default_materials()

    return app


def _create_default_admin(app):
    from app.models import User
    admin = User.query.filter_by(email='admin@muebles.com').first()
    if not admin:
        temp_password = secrets.token_urlsafe(16)
        admin = User(
            username='admin',
            email='admin@muebles.com',
            is_admin=True
        )
        admin.set_password(temp_password)
        db.session.add(admin)
        db.session.commit()
        logging.getLogger(__name__).warning(
            "\n" + "=" * 60 +
            f"\nAdmin account created."
            f"\n  email:    admin@muebles.com"
            f"\n  password: {temp_password}"
            f"\nCHANGE THIS PASSWORD IMMEDIATELY after first login."
            "\n" + "=" * 60
        )


def _create_default_categories():
    from app.models import Category
    defaults = [
        ('Sillas', 'sillas', 'Todo tipo de sillas'),
        ('Sillones', 'sillones', 'Sillones cómodos para tu hogar'),
        ('Mesas', 'mesas', 'Mesas de todos los tamaños'),
        ('Estanterías', 'estanterias', 'Estanterías y organizadores'),
        ('Bancos', 'bancos', 'Bancos y banquetas'),
    ]
    for name, slug, desc in defaults:
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name=name, slug=slug, description=desc))
    db.session.commit()


def _create_default_materials():
    from app.models import Material
    defaults = ['Plástico', 'Madera']
    for name in defaults:
        if not Material.query.filter_by(name=name).first():
            db.session.add(Material(name=name))
    db.session.commit()
