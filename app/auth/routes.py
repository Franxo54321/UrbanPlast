import secrets
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter
from app.models import User
from app.auth.forms import LoginForm, RegisterForm, ProfileForm, ChangePasswordForm

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
        mail_configured = bool(current_app.config.get('MAIL_USERNAME'))
        token = secrets.token_urlsafe(32) if mail_configured else None
        user = User(
            username=form.username.data,
            email=form.email.data,
            email_verified=not mail_configured,
            verification_token=token
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        if mail_configured:
            import threading
            _app = current_app._get_current_object()
            threading.Thread(
                target=_send_verification_email,
                args=(user.id, _app),
                daemon=True
            ).start()
            flash('¡Cuenta creada! Te enviamos un email para verificar tu cuenta.', 'success')
        else:
            flash('¡Cuenta creada! Ya podés iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/verificar/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('El link de verificación es inválido o ya fue usado.', 'danger')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    user.verification_token = None
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
        db.session.commit()
        import threading
        _app = current_app._get_current_object()
        threading.Thread(
            target=_send_verification_email,
            args=(user.id, _app),
            daemon=True
        ).start()
    flash('Si el email existe y no está verificado, te reenviamos el link.', 'info')
    return redirect(url_for('auth.login'))


def _send_verification_email(user_id, app):
    from app import mail
    from app.models import User as _User
    import logging
    with app.app_context():
        try:
            from flask_mail import Message
            user = db.session.get(_User, user_id)
            if not user or not user.verification_token:
                return
            base_url = app.config.get('BASE_URL', '').rstrip('/')
            verify_url = f"{base_url}/auth/verificar/{user.verification_token}"
            html = render_template('emails/verify_email.html',
                                   username=user.username,
                                   verify_url=verify_url,
                                   now=datetime.utcnow())
            msg = Message(
                subject='UrbanPlast — Verificá tu cuenta',
                recipients=[user.email],
                html=html
            )
            mail.send(msg)
        except Exception as e:
            logging.getLogger(__name__).error(f'Error enviando email de verificación: {e}')


@auth_bp.route('/logout')
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
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Datos actualizados correctamente.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html', form=form)


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
