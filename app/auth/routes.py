import re
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter, oauth
from app.models import User
from app.auth.forms import LoginForm, RegisterForm, ProfileForm, ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm

auth_bp = Blueprint('auth', __name__, template_folder='templates')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            if not user.email_verified:
                flash('Tenés que verificar tu email antes de iniciar sesión. Revisá tu bandeja de entrada.', 'warning')
                return render_template('auth/login.html', form=form)
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            if next_page and not _is_safe_url(next_page):
                next_page = None
            flash('¡Bienvenido!', 'success')
            return redirect(next_page or url_for('main.index'))
        flash('Email o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegisterForm()
    if form.validate_on_submit():
        from app.email_utils import is_email_configured
        mail_configured = is_email_configured()
        token = secrets.token_urlsafe(32) if mail_configured else None
        token_expiry = datetime.utcnow() + timedelta(hours=24) if mail_configured else None
        user = User(
            username=form.username.data,
            email=form.email.data,
            email_verified=not mail_configured,
            verification_token=token,
            verification_token_expiry=token_expiry,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        if mail_configured:
            _app = current_app._get_current_object()
            base_url = current_app.config.get('BASE_URL', '').rstrip('/')
            verify_url = f"{base_url}/auth/verificar/{token}"
            html = render_template('emails/verify_email.html',
                                   username=user.username,
                                   verify_url=verify_url,
                                   now=datetime.utcnow())
            _send_email_bg(_app, user.email, 'UrbanPlast — Verificá tu cuenta', html)
            flash('¡Cuenta creada! Te enviamos un email para verificar tu cuenta.', 'success')
        else:
            flash('¡Cuenta creada! Ya podés iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/verificar/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user or (user.verification_token_expiry and user.verification_token_expiry < datetime.utcnow()):
        flash('El link de verificación es inválido o expiró (válido por 24 horas).', 'danger')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    user.verification_token = None
    user.verification_token_expiry = None
    db.session.commit()
    flash('¡Email verificado! Ya podés iniciar sesión.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/reenviar-verificacion', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verification():
    email = request.form.get('email', '').strip()
    user = User.query.filter_by(email=email).first()
    if user and not user.email_verified:
        token = secrets.token_urlsafe(32)
        user.verification_token = token
        user.verification_token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        _app = current_app._get_current_object()
        base_url = current_app.config.get('BASE_URL', '').rstrip('/')
        verify_url = f"{base_url}/auth/verificar/{token}"
        html = render_template('emails/verify_email.html',
                               username=user.username,
                               verify_url=verify_url,
                               now=datetime.utcnow())
        _send_email_bg(_app, user.email, 'UrbanPlast — Verificá tu cuenta', html)
    flash('Si el email existe y no está verificado, te reenviamos el link.', 'info')
    return redirect(url_for('auth.login'))


def _send_email_bg(app, recipient, subject, html):
    """Send email in background thread. HTML must be pre-rendered in request context."""
    import threading
    import logging

    def _bg():
        from app.email_utils import send_email
        try:
            send_email(subject=subject, recipients=[recipient], html=html, app=app)
        except Exception as e:
            logging.getLogger(__name__).error(f'Error enviando email a {recipient}: {e}')

    threading.Thread(target=_bg, daemon=True).start()


@auth_bp.route('/recuperar', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip()).first()
        if user and user.email_verified:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=2)
            db.session.commit()
            _app = current_app._get_current_object()
            base_url = current_app.config.get('BASE_URL', '').rstrip('/')
            reset_url = f"{base_url}/auth/reset/{token}"
            html = render_template('emails/reset_password.html',
                                   username=user.username,
                                   reset_url=reset_url,
                                   now=datetime.utcnow())
            _send_email_bg(_app, user.email, 'UrbanPlast — Recuperar contraseña', html)
        flash('Si el email existe y está verificado, te enviamos el link de recuperación.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('El link de recuperación es inválido o expiró (válido por 2 horas).', 'danger')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('¡Contraseña cambiada! Ya podés iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        if form.username.data != current_user.username:
            existing = User.query.filter_by(username=form.username.data).first()
            if existing:
                flash('Ese nombre de usuario ya está en uso.', 'danger')
                return render_template('auth/profile.html', form=form)
        if form.email.data != current_user.email:
            existing = User.query.filter_by(email=form.email.data).first()
            if existing:
                flash('Ese email ya está registrado.', 'danger')
                return render_template('auth/profile.html', form=form)

        # Avatar upload
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            saved = _save_user_avatar(avatar_file)
            if saved:
                current_user.avatar = saved

        current_user.username    = form.username.data
        current_user.email       = form.email.data
        current_user.full_name   = form.full_name.data
        current_user.phone       = form.phone.data
        current_user.birth_date  = form.birth_date.data
        current_user.dni         = form.dni.data
        current_user.address     = form.address.data
        current_user.city        = form.city.data
        current_user.province    = form.province.data
        current_user.postal_code = form.postal_code.data
        current_user.country     = form.country.data
        db.session.commit()
        flash('Datos actualizados correctamente.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html', form=form)


def _save_user_avatar(file):
    from werkzeug.utils import secure_filename
    import uuid as _uuid
    from flask import current_app
    if not file or file.filename == '':
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
        return None
    file_bytes = file.read()
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(file_bytes))
        img.verify()
    except Exception:
        return None
    unique_name = f"avatar_{_uuid.uuid4().hex}.{ext}"
    import os
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
    with open(filepath, 'wb') as out:
        out.write(file_bytes)
    return unique_name


@auth_bp.route('/cambiar-contrasena', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('La contraseña actual es incorrecta.', 'danger')
            return render_template('auth/change_password.html', form=form)
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash('Contraseña cambiada exitosamente.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/change_password.html', form=form)


def _is_safe_url(target):
    from urllib.parse import urlparse
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ('', 'http', 'https') and ref_url.netloc == test_url.netloc


# ──────────────────── Google OAuth ────────────────────

@auth_bp.route('/google')
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    base = current_app.config.get('BASE_URL', '').rstrip('/')
    redirect_uri = f"{base}/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash('Error al autenticar con Google. Intentá de nuevo.', 'danger')
        return redirect(url_for('auth.login'))

    info = token.get('userinfo')
    if not info or not info.get('email'):
        flash('No se pudo obtener la información de tu cuenta de Google.', 'danger')
        return redirect(url_for('auth.login'))

    google_id = info['sub']
    email = info['email']

    # Buscar por google_id primero, luego por email
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            # Vincular cuenta existente
            user.google_id = google_id
            if not user.email_verified:
                user.email_verified = True
            db.session.commit()
        else:
            # Crear nuevo usuario
            base = re.sub(r'[^a-z0-9_.-]', '', email.split('@')[0].lower())[:40] or 'user'
            username = base
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f'{base}{counter}'
                counter += 1

            user = User(
                username=username,
                email=email,
                email_verified=True,
                google_id=google_id,
            )
            user.set_password(secrets.token_urlsafe(32))
            db.session.add(user)
            db.session.commit()

    login_user(user)
    flash('¡Bienvenido!', 'success')
    next_page = request.args.get('next')
    if next_page and not _is_safe_url(next_page):
        next_page = None
    return redirect(next_page or url_for('main.index'))
