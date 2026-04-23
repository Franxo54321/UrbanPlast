from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class ContactForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    subject = StringField('Asunto', validators=[DataRequired(), Length(max=200)])
    message = TextAreaField('Mensaje', validators=[DataRequired(), Length(min=10, max=2000)])
    submit = SubmitField('Enviar mensaje')
