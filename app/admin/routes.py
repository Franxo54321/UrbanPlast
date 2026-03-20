import os
import uuid
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Product, Category, User, CartItem, Order, OrderItem, Material, Color, ProductImage
from app.admin.forms import ProductForm, ColorForm, MaterialForm, CategoryForm

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


# ──────────────────── Dashboard ────────────────────

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


# ──────────────────── Productos ────────────────────

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
    form.material_id.choices = [(m.id, m.name) for m in Material.query.order_by(Material.name).all()]
    form.color_ids.choices = [(c.id, c.name) for c in Color.query.order_by(Color.name).all()]

    if form.validate_on_submit():
        slug = _slugify(form.name.data)
        existing = Product.query.filter_by(slug=slug).first()
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        mat = Material.query.get(form.material_id.data)
        product = Product(
            name=form.name.data,
            slug=slug,
            description=form.description.data,
            price=form.price.data,
            stock=form.stock.data,
            material=mat.name if mat else '',
            material_id=form.material_id.data,
            category_id=form.category_id.data,
            featured=form.featured.data,
            active=form.active.data,
        )

        # Colores
        selected_colors = Color.query.filter(Color.id.in_(form.color_ids.data)).all()
        product.colors = selected_colors

        db.session.add(product)
        db.session.flush()

        # Imágenes múltiples
        files = request.files.getlist('images')
        pos = 0
        for f in files:
            saved = _save_image(f)
            if saved:
                db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos))
                pos += 1

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
    form.material_id.choices = [(m.id, m.name) for m in Material.query.order_by(Material.name).all()]
    form.color_ids.choices = [(c.id, c.name) for c in Color.query.order_by(Color.name).all()]

    if request.method == 'GET':
        form.material_id.data = product.material_id
        form.color_ids.data = [c.id for c in product.colors]

    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.stock = form.stock.data
        product.material_id = form.material_id.data
        mat = Material.query.get(form.material_id.data)
        product.material = mat.name if mat else ''
        product.category_id = form.category_id.data
        product.featured = form.featured.data
        product.active = form.active.data

        # Colores
        selected_colors = Color.query.filter(Color.id.in_(form.color_ids.data)).all()
        product.colors = selected_colors

        # Eliminar imágenes marcadas
        deleted_ids = request.form.getlist('delete_images')
        if deleted_ids:
            for img_id in deleted_ids:
                img = ProductImage.query.get(int(img_id))
                if img and img.product_id == product.id:
                    path = os.path.join(current_app.config['UPLOAD_FOLDER'], img.filename)
                    if os.path.exists(path):
                        os.remove(path)
                    db.session.delete(img)

        # Nuevas imágenes
        files = request.files.getlist('images')
        last_pos = db.session.query(db.func.coalesce(db.func.max(ProductImage.position), -1)).filter_by(product_id=product.id).scalar()
        pos = (last_pos or -1) + 1
        for f in files:
            saved = _save_image(f)
            if saved:
                db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos))
                pos += 1

        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/product_form.html', form=form, editing=True, product=product)


@admin_bp.route('/productos/<int:product_id>/eliminar', methods=['POST'])
@admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)

    CartItem.query.filter_by(product_id=product.id).delete()

    # Borrar imágenes del filesystem
    for img in product.images.all():
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], img.filename)
        if os.path.exists(path):
            os.remove(path)

    if product.image:
        img_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado.', 'success')
    return jsonify({'success': True})


# ──────────────────── Colores ────────────────────

@admin_bp.route('/colores')
@admin_required
def colors():
    all_colors = Color.query.order_by(Color.name).all()
    return render_template('admin/colors.html', colors=all_colors)


@admin_bp.route('/colores/nuevo', methods=['GET', 'POST'])
@admin_required
def color_create():
    form = ColorForm()
    if form.validate_on_submit():
        if Color.query.filter_by(name=form.name.data).first():
            flash('Ya existe un color con ese nombre.', 'warning')
        else:
            db.session.add(Color(name=form.name.data, hex_code=form.hex_code.data))
            db.session.commit()
            flash('Color creado.', 'success')
            return redirect(url_for('admin.colors'))
    return render_template('admin/color_form.html', form=form, editing=False)


@admin_bp.route('/colores/<int:color_id>/editar', methods=['GET', 'POST'])
@admin_required
def color_edit(color_id):
    color = Color.query.get_or_404(color_id)
    form = ColorForm(obj=color)
    if form.validate_on_submit():
        color.name = form.name.data
        color.hex_code = form.hex_code.data
        db.session.commit()
        flash('Color actualizado.', 'success')
        return redirect(url_for('admin.colors'))
    return render_template('admin/color_form.html', form=form, editing=True, color=color)


@admin_bp.route('/colores/<int:color_id>/eliminar', methods=['POST'])
@admin_required
def color_delete(color_id):
    color = Color.query.get_or_404(color_id)
    db.session.delete(color)
    db.session.commit()
    flash('Color eliminado.', 'success')
    return redirect(url_for('admin.colors'))


# ──────────────────── Materiales ────────────────────

@admin_bp.route('/materiales')
@admin_required
def materials():
    all_materials = Material.query.order_by(Material.name).all()
    return render_template('admin/materials.html', materials=all_materials)


@admin_bp.route('/materiales/nuevo', methods=['GET', 'POST'])
@admin_required
def material_create():
    form = MaterialForm()
    if form.validate_on_submit():
        if Material.query.filter_by(name=form.name.data).first():
            flash('Ya existe un material con ese nombre.', 'warning')
        else:
            db.session.add(Material(name=form.name.data))
            db.session.commit()
            flash('Material creado.', 'success')
            return redirect(url_for('admin.materials'))
    return render_template('admin/material_form.html', form=form, editing=False)


@admin_bp.route('/materiales/<int:material_id>/editar', methods=['GET', 'POST'])
@admin_required
def material_edit(material_id):
    mat = Material.query.get_or_404(material_id)
    form = MaterialForm(obj=mat)
    if form.validate_on_submit():
        mat.name = form.name.data
        db.session.commit()
        flash('Material actualizado.', 'success')
        return redirect(url_for('admin.materials'))
    return render_template('admin/material_form.html', form=form, editing=True, material=mat)


@admin_bp.route('/materiales/<int:material_id>/eliminar', methods=['POST'])
@admin_required
def material_delete(material_id):
    mat = Material.query.get_or_404(material_id)
    db.session.delete(mat)
    db.session.commit()
    flash('Material eliminado.', 'success')
    return redirect(url_for('admin.materials'))


# ──────────────────── Categorías ────────────────────

@admin_bp.route('/categorias')
@admin_required
def categories_list():
    all_cats = Category.query.order_by(Category.name).all()
    return render_template('admin/categories.html', categories=all_cats)


@admin_bp.route('/categorias/nuevo', methods=['GET', 'POST'])
@admin_required
def category_create():
    form = CategoryForm()
    if form.validate_on_submit():
        slug = _slugify(form.name.data)
        if Category.query.filter_by(slug=slug).first():
            flash('Ya existe una categoría con ese nombre.', 'warning')
        else:
            db.session.add(Category(name=form.name.data, slug=slug, description=form.description.data))
            db.session.commit()
            flash('Categoría creada.', 'success')
            return redirect(url_for('admin.categories_list'))
    return render_template('admin/category_form.html', form=form, editing=False)


@admin_bp.route('/categorias/<int:cat_id>/editar', methods=['GET', 'POST'])
@admin_required
def category_edit(cat_id):
    cat = Category.query.get_or_404(cat_id)
    form = CategoryForm(obj=cat)
    if form.validate_on_submit():
        cat.name = form.name.data
        cat.slug = _slugify(form.name.data)
        cat.description = form.description.data
        db.session.commit()
        flash('Categoría actualizada.', 'success')
        return redirect(url_for('admin.categories_list'))
    return render_template('admin/category_form.html', form=form, editing=True, category=cat)


@admin_bp.route('/categorias/<int:cat_id>/eliminar', methods=['POST'])
@admin_required
def category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if cat.products.count() > 0:
        flash('No se puede eliminar una categoría con productos asignados.', 'danger')
        return redirect(url_for('admin.categories_list'))
    db.session.delete(cat)
    db.session.commit()
    flash('Categoría eliminada.', 'success')
    return redirect(url_for('admin.categories_list'))


# ──────────────────── Pedidos ────────────────────

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
