from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
from app.models import User


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')


class RegisterForm(FlaskForm):
    username = StringField('Usuario', validators=[
        DataRequired(), Length(min=3, max=80)
    ])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[
        DataRequired(), Length(min=6, message='La contraseña debe tener al menos 6 caracteres')
    ])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(), EqualTo('password', message='Las contraseñas no coinciden')
    ])
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Ese nombre de usuario ya está en uso.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Ese email ya está registrado.')


class ProfileForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Guardar cambios')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Contraseña actual', validators=[DataRequired()])
    new_password = PasswordField('Nueva contraseña', validators=[
        DataRequired(), Length(min=6, message='Mínimo 6 caracteres')
    ])
    confirm_password = PasswordField('Confirmar nueva contraseña', validators=[
        DataRequired(), EqualTo('new_password', message='Las contraseñas no coinciden')
    ])
    submit = SubmitField('Cambiar contraseña')


class CheckoutForm(FlaskForm):
    delivery_type = SelectField('Tipo de entrega', choices=[
        ('envio', '📦 Envío a domicilio'),
        ('retiro', '🏪 Retiro en sucursal'),
    ], validators=[DataRequired()])
    address = StringField('Dirección', validators=[DataRequired(), Length(max=300)])
    city = StringField('Ciudad', validators=[DataRequired(), Length(max=100)])
    province = StringField('Provincia', validators=[DataRequired(), Length(max=100)])
    postal_code = StringField('Código Postal', validators=[DataRequired(), Length(max=20)])
    country = StringField('País', validators=[Optional(), Length(max=100)], default='Argentina')
    phone = StringField('Teléfono', validators=[DataRequired(), Length(max=50)])
    payment_method = SelectField('Método de pago', choices=[
        ('mercadopago', '💙 MercadoPago'),
        ('tarjeta', '💳 Tarjeta de Crédito / Débito'),
        ('transferencia', '🏦 Transferencia Bancaria'),
    ], validators=[DataRequired()])
    notes = TextAreaField('Notas (opcional)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Confirmar pedido')
