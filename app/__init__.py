import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

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

    with app.app_context():
        db.create_all()
        _create_default_admin(app)
        _create_default_categories()

    return app


def _create_default_admin(app):
    from app.models import User
    admin = User.query.filter_by(email='admin@muebles.com').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@muebles.com',
            is_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()


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
