from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, MultipleFileField
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, SelectField, BooleanField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Length, NumberRange, Regexp, Optional
from wtforms.widgets import CheckboxInput, ListWidget


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class ProductForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Descripción')
    price = DecimalField('Precio', validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    stock = IntegerField('Stock', validators=[DataRequired(), NumberRange(min=0)], default=0)
    material_id = SelectField('Material', coerce=int, validators=[DataRequired()])
    category_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    color_ids = MultiCheckboxField('Colores', coerce=int)
    featured = BooleanField('Producto destacado')
    active = BooleanField('Activo', default=True)
    images = MultipleFileField('Imágenes', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Solo imágenes (jpg, png, webp)')
    ])
    submit = SubmitField('Guardar')


class ColorForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    hex_code = StringField('Color (hex)', validators=[
        DataRequired(), Regexp(r'^#[0-9a-fA-F]{6}$', message='Formato: #RRGGBB')
    ])
    submit = SubmitField('Guardar')


class MaterialForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Guardar')


class CategoryForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Descripción', validators=[Optional()])
    submit = SubmitField('Guardar')
