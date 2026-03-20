from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange


class ProductForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Descripción')
    price = DecimalField('Precio', validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    stock = IntegerField('Stock', validators=[DataRequired(), NumberRange(min=0)], default=0)
    material = SelectField('Material', choices=[
        ('plastico', 'Plástico'),
        ('madera', 'Madera')
    ], validators=[DataRequired()])
    category_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    featured = BooleanField('Producto destacado')
    active = BooleanField('Activo', default=True)
    image = FileField('Imagen', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Solo imágenes (jpg, png, webp)')
    ])
    submit = SubmitField('Guardar')
