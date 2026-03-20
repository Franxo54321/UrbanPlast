import os
import uuid
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Product, Category, User, CartItem, Order, OrderItem
from app.admin.forms import ProductForm

admin_bp = Blueprint('admin', __name__, template_folder='templates')


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('No tenés permiso para acceder a esta sección.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def _save_image(file):
    if not file or file.filename == '':
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in current_app.config['ALLOWED_EXTENSIONS']:
        return None
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    return unique_name


def _slugify(text):
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[áàäâ]', 'a', slug)
    slug = re.sub(r'[éèëê]', 'e', slug)
    slug = re.sub(r'[íìïî]', 'i', slug)
    slug = re.sub(r'[óòöô]', 'o', slug)
    slug = re.sub(r'[úùüû]', 'u', slug)
    slug = re.sub(r'[ñ]', 'n', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')


@admin_bp.route('/')
@admin_required
def dashboard():
    total_products = Product.query.count()
    total_users = User.query.count()
    total_categories = Category.query.count()
    total_orders = Order.query.count()
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(5).all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_users=total_users,
                           total_categories=total_categories,
                           total_orders=total_orders,
                           recent_products=recent_products,
                           recent_orders=recent_orders)


@admin_bp.route('/productos')
@admin_required
def products():
    page = request.args.get('page', 1, type=int)
    products = Product.query.order_by(Product.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/products.html', products=products)


@admin_bp.route('/productos/nuevo', methods=['GET', 'POST'])
@admin_required
def product_create():
    form = ProductForm()
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]

    if form.validate_on_submit():
        slug = _slugify(form.name.data)
        existing = Product.query.filter_by(slug=slug).first()
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        image_name = _save_image(form.image.data)

        product = Product(
            name=form.name.data,
            slug=slug,
            description=form.description.data,
            price=form.price.data,
            stock=form.stock.data,
            material=form.material.data,
            category_id=form.category_id.data,
            featured=form.featured.data,
            active=form.active.data,
            image=image_name
        )
        db.session.add(product)
        db.session.commit()
        flash('Producto creado exitosamente.', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/product_form.html', form=form, editing=False)


@admin_bp.route('/productos/<int:product_id>/editar', methods=['GET', 'POST'])
@admin_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]

    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.stock = form.stock.data
        product.material = form.material.data
        product.category_id = form.category_id.data
        product.featured = form.featured.data
        product.active = form.active.data

        if form.image.data and hasattr(form.image.data, 'filename') and form.image.data.filename:
            if product.image:
                old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            product.image = _save_image(form.image.data)

        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/product_form.html', form=form, editing=True, product=product)


@admin_bp.route('/productos/<int:product_id>/eliminar', methods=['POST'])
@admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)

    CartItem.query.filter_by(product_id=product.id).delete()

    if product.image:
        img_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado.', 'success')
    return jsonify({'success': True})


@admin_bp.route('/pedidos')
@admin_required
def orders():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('estado', '')
    query = Order.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    orders = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/orders.html', orders=orders, current_status=status_filter)


@admin_bp.route('/pedidos/<int:order_id>')
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/order_detail.html', order=order)


@admin_bp.route('/pedidos/<int:order_id>/estado', methods=['POST'])
@admin_required
def order_update_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status', '')
    valid_statuses = ['pendiente', 'pagado', 'enviado', 'completado', 'cancelado']
    if new_status in valid_statuses:
        order.status = new_status
        db.session.commit()
        flash(f'Estado del pedido #{order.id} actualizado a "{new_status}".', 'success')
    else:
        flash('Estado inválido.', 'danger')
    return redirect(url_for('admin.order_detail', order_id=order.id))
