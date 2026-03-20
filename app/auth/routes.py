from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
from app.auth.forms import LoginForm, RegisterForm, ProfileForm, ChangePasswordForm

auth_bp = Blueprint('auth', __name__, template_folder='templates')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            if next_page and not _is_safe_url(next_page):
                next_page = None
            flash('¡Bienvenido!', 'success')
            return redirect(next_page or url_for('main.index'))
        flash('Email o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('¡Cuenta creada! Ya podés iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


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
