import os
import uuid
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from app import db
from app.models import (Product, Category, User, CartItem, Order, OrderItem,
                        Material, Color, ProductImage, Coupon, OrderStatusHistory,
                        SiteSetting)
from app.admin.forms import ProductForm, ColorForm, MaterialForm, CategoryForm, CouponForm

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


def _safe_remove(filename):
    """Elimina archivo del UPLOAD_FOLDER validando que no haya path traversal."""
    upload_dir = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
    target = os.path.realpath(os.path.join(upload_dir, filename))
    if not target.startswith(upload_dir + os.sep):
        return
    if os.path.exists(target):
        os.remove(target)


def _save_image(file):
    if not file or file.filename == '':
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in current_app.config['ALLOWED_EXTENSIONS']:
        return None

    file_bytes = file.read()

    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(file_bytes))
        img.verify()
        img = Image.open(_io.BytesIO(file_bytes))
        if img.mode in ('RGBA', 'P') and ext in ('jpg', 'jpeg'):
            img = img.convert('RGB')
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        img.save(filepath, optimize=True)
        return unique_name
    except Exception:
        return None


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

    # Ingresos del mes actual
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_revenue = db.session.query(func.sum(Order.total)).filter(
        Order.created_at >= month_start,
        Order.status.in_(['pagado', 'enviado', 'completado'])
    ).scalar() or 0

    # Pedidos por estado
    status_counts = dict(db.session.query(Order.status, func.count(Order.id))
                         .group_by(Order.status).all())

    # Productos más vendidos (top 5)
    top_products = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity).label('total_qty')
    ).group_by(OrderItem.product_name)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(5).all()

    # Ventas últimos 6 meses para gráfico
    sales_data = []
    for i in range(5, -1, -1):
        d = now - timedelta(days=30 * i)
        m_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if d.month == 12:
            m_end = d.replace(year=d.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            m_end = d.replace(month=d.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        revenue = db.session.query(func.sum(Order.total)).filter(
            Order.created_at >= m_start,
            Order.created_at < m_end,
            Order.status.in_(['pagado', 'enviado', 'completado'])
        ).scalar() or 0
        sales_data.append({
            'month': d.strftime('%b %Y'),
            'revenue': float(revenue)
        })

    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_users=total_users,
                           total_categories=total_categories,
                           total_orders=total_orders,
                           recent_products=recent_products,
                           recent_orders=recent_orders,
                           monthly_revenue=monthly_revenue,
                           status_counts=status_counts,
                           top_products=top_products,
                           sales_data=sales_data)


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

        selected_colors = Color.query.filter(Color.id.in_(form.color_ids.data)).all()
        product.colors = selected_colors

        db.session.add(product)
        db.session.flush()

        files = request.files.getlist('images')
        pos = 0
        for f in files:
            saved = _save_image(f)
            if saved:
                db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos))
                pos += 1

        # Color-specific images
        for color in selected_colors:
            color_file = request.files.get(f'color_image_{color.id}')
            if color_file and color_file.filename:
                saved = _save_image(color_file)
                if saved:
                    # Replace existing color image if any
                    existing = ProductImage.query.filter_by(product_id=product.id, color_id=color.id).first()
                    if existing:
                        _safe_remove(existing.filename)
                        existing.filename = saved
                    else:
                        db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos, color_id=color.id))
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

        selected_colors = Color.query.filter(Color.id.in_(form.color_ids.data)).all()
        product.colors = selected_colors

        deleted_ids = request.form.getlist('delete_images')
        if deleted_ids:
            for img_id in deleted_ids:
                img = ProductImage.query.get(int(img_id))
                if img and img.product_id == product.id:
                    _safe_remove(img.filename)
                    db.session.delete(img)

        files = request.files.getlist('images')
        last_pos = db.session.query(db.func.coalesce(db.func.max(ProductImage.position), -1)).filter_by(product_id=product.id).scalar()
        pos = (last_pos or -1) + 1
        for f in files:
            saved = _save_image(f)
            if saved:
                db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos))
                pos += 1

        # Color-specific images
        for color in selected_colors:
            color_file = request.files.get(f'color_image_{color.id}')
            if color_file and color_file.filename:
                saved = _save_image(color_file)
                if saved:
                    existing = ProductImage.query.filter_by(product_id=product.id, color_id=color.id).first()
                    if existing:
                        _safe_remove(existing.filename)
                        existing.filename = saved
                    else:
                        db.session.add(ProductImage(product_id=product.id, filename=saved, position=pos, color_id=color.id))
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

    for img in product.images.all():
        _safe_remove(img.filename)

    if product.image:
        _safe_remove(product.image)

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


# ──────────────────── Cupones ────────────────────

@admin_bp.route('/cupones')
@admin_required
def coupons():
    all_coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('admin/coupons.html', coupons=all_coupons)


@admin_bp.route('/cupones/nuevo', methods=['GET', 'POST'])
@admin_required
def coupon_create():
    form = CouponForm()
    if form.validate_on_submit():
        code = form.code.data.strip().upper()
        if Coupon.query.filter_by(code=code).first():
            flash('Ya existe un cupón con ese código.', 'warning')
        else:
            db.session.add(Coupon(
                code=code,
                discount_type=form.discount_type.data,
                discount_value=form.discount_value.data,
                active=form.active.data,
                uses_left=form.uses_left.data or None,
                min_order=form.min_order.data or 0,
            ))
            db.session.commit()
            flash('Cupón creado.', 'success')
            return redirect(url_for('admin.coupons'))
    return render_template('admin/coupon_form.html', form=form, editing=False)


@admin_bp.route('/cupones/<int:coupon_id>/editar', methods=['GET', 'POST'])
@admin_required
def coupon_edit(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    form = CouponForm(obj=coupon)
    if form.validate_on_submit():
        coupon.code = form.code.data.strip().upper()
        coupon.discount_type = form.discount_type.data
        coupon.discount_value = form.discount_value.data
        coupon.active = form.active.data
        coupon.uses_left = form.uses_left.data or None
        coupon.min_order = form.min_order.data or 0
        db.session.commit()
        flash('Cupón actualizado.', 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/coupon_form.html', form=form, editing=True, coupon=coupon)


@admin_bp.route('/cupones/<int:coupon_id>/eliminar', methods=['POST'])
@admin_required
def coupon_delete(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    flash('Cupón eliminado.', 'success')
    return redirect(url_for('admin.coupons'))


# ──────────────────── Usuarios ────────────────────

@admin_bp.route('/usuarios')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/usuarios/<int:user_id>/eliminar', methods=['POST'])
@admin_required
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('No podés eliminar una cuenta de administrador.', 'danger')
        return redirect(url_for('admin.users'))
    db.session.delete(user)
    db.session.commit()
    flash(f'Usuario {user.email} eliminado.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/usuarios/<int:user_id>/resetear-contrasena', methods=['POST'])
@admin_required
def user_reset_password(user_id):
    import secrets as _secrets
    user = User.query.get_or_404(user_id)
    new_password = _secrets.token_urlsafe(10)
    user.set_password(new_password)
    db.session.commit()

    try:
        from app.email_utils import send_email, is_email_configured
        if is_email_configured():
            html = (
                f'<p>Hola <strong>{user.username}</strong>,</p>'
                f'<p>Un administrador reseteó tu contraseña en UrbanPlast.</p>'
                f'<p>Tu nueva contraseña temporal es: <strong style="font-size:18px;">{new_password}</strong></p>'
                f'<p>Por favor cambiala desde tu perfil una vez que ingreses.</p>'
            )
            send_email(
                subject='UrbanPlast — Tu contraseña fue reseteada',
                recipients=[user.email],
                html=html
            )
            flash(f'Contraseña reseteada y enviada por email a {user.email}.', 'success')
        else:
            flash(f'Contraseña reseteada. Nueva contraseña: {new_password}', 'warning')
    except Exception:
        flash(f'Contraseña reseteada. Nueva contraseña: {new_password}', 'warning')

    return redirect(url_for('admin.users'))


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
    history = order.status_history.order_by(OrderStatusHistory.changed_at).all()
    return render_template('admin/order_detail.html', order=order, history=history)


@admin_bp.route('/pedidos/<int:order_id>/estado', methods=['POST'])
@admin_required
def order_update_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status', '')
    tracking = request.form.get('tracking_number', '').strip()
    note = request.form.get('note', '').strip()

    valid_statuses = ['pendiente', 'pagado', 'enviado', 'completado', 'cancelado']
    if new_status in valid_statuses:
        changed = order.status != new_status
        order.status = new_status
        if tracking:
            order.tracking_number = tracking
        if changed:
            db.session.add(OrderStatusHistory(
                order_id=order.id,
                status=new_status,
                note=note or None
            ))
        db.session.commit()

        if changed and new_status in ('pagado', 'enviado', 'completado', 'cancelado'):
            _notify_order_status(order, new_status, note, tracking)

        flash(f'Pedido #{order.id} actualizado a "{new_status}".', 'success')
    else:
        flash('Estado inválido.', 'danger')
    return redirect(url_for('admin.order_detail', order_id=order.id))


def _notify_order_status(order, status, note, tracking):
    from app.email_utils import send_email, is_email_configured
    if not is_email_configured():
        return
    try:
        base = current_app.config.get('BASE_URL', '').rstrip('/')
        order_url = f"{base}/mis-pedidos/{order.id}"
        html = render_template('emails/order_status.html',
                               order=order,
                               status=status,
                               note=note or None,
                               tracking=tracking or None,
                               order_url=order_url,
                               now=datetime.utcnow())
        _app = current_app._get_current_object()
        recipient = order.user.email

        import threading
        def _bg():
            send_email(
                subject=f'UrbanPlast — Pedido #{order.id}: {status}',
                recipients=[recipient],
                html=html,
                app=_app
            )
        threading.Thread(target=_bg, daemon=True).start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Error enviando notificación de pedido: {e}')


# ──────────────────── Test Email ────────────────────

def _get_mail_config_info(app):
    from app.email_utils import is_email_configured
    return {
        'MAIL_SERVER': app.config.get('MAIL_SERVER', ''),
        'MAIL_PORT': app.config.get('MAIL_PORT', ''),
        'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS', ''),
        'MAIL_USE_SSL': app.config.get('MAIL_USE_SSL', False),
        'MAIL_USERNAME': app.config.get('MAIL_USERNAME', '') or '',
        'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER', ''),
        'BREVO_API_KEY': '••••••••' if app.config.get('BREVO_API_KEY') else '(no configurado)',
        'brevo_configured': bool(app.config.get('BREVO_API_KEY')),
        'mail_configured': is_email_configured(app),
    }


def _smtp_ping(host, port, timeout=8):
    import socket
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True, None
    except socket.timeout:
        return False, f'Timeout: no se pudo conectar a {host}:{port} en {timeout}s (puerto bloqueado)'
    except OSError as e:
        return False, f'Error de conexión a {host}:{port} — {e}'


@admin_bp.route('/test-email/ping')
@admin_required
def test_email_ping():
    app = current_app._get_current_object()
    if app.config.get('BREVO_API_KEY'):
        # Con Brevo API key, probamos el endpoint HTTP (no SMTP)
        import requests as _req
        try:
            r = _req.get('https://api.brevo.com/v3/account',
                         headers={'api-key': app.config['BREVO_API_KEY']},
                         timeout=8)
            if r.status_code == 200:
                data = r.json()
                return jsonify({'ok': True, 'mode': 'brevo_api',
                                'info': f"Cuenta: {data.get('email', '')} — Plan: {data.get('plan', [{}])[0].get('type', '?')}"})
            return jsonify({'ok': False, 'mode': 'brevo_api',
                            'error': f'Brevo API respondió {r.status_code}: {r.text[:200]}'})
        except Exception as e:
            return jsonify({'ok': False, 'mode': 'brevo_api', 'error': str(e)})
    else:
        host = app.config.get('MAIL_SERVER', '')
        port = int(app.config.get('MAIL_PORT', 587))
        ok, err = _smtp_ping(host, port)
        return jsonify({'ok': ok, 'mode': 'smtp', 'host': host, 'port': port, 'error': err})


@admin_bp.route('/test-email', methods=['GET', 'POST'])
@admin_required
def test_email():
    from app.email_utils import send_email

    config_info = _get_mail_config_info(current_app)
    result = None

    if request.method == 'POST':
        recipient = request.form.get('recipient', '').strip()
        subject = request.form.get('subject', 'Test de email — UrbanPlast').strip()
        body = request.form.get('body', 'Este es un email de prueba.').strip()

        if not recipient:
            flash('Ingresá un destinatario.', 'danger')
        elif not config_info['mail_configured']:
            flash('No hay proveedor de email configurado (BREVO_API_KEY ni MAIL_USERNAME).', 'danger')
        else:
            html = f'<p>{body}</p><hr><small>Panel admin — UrbanPlast</small>'
            ok = send_email(subject=subject, recipients=[recipient], html=html)
            if ok:
                result = {'ok': True, 'recipient': recipient}
                flash(f'Email enviado correctamente a {recipient}.', 'success')
            else:
                result = {'ok': False, 'error': 'Error al enviar. Revisá los logs del servidor para el detalle.'}
                flash('Error al enviar. Ver detalles abajo.', 'danger')

    return render_template('admin/test_email.html',
                           active_page='test_email',
                           config_info=config_info,
                           result=result)


@admin_bp.route('/hero-image', methods=['GET', 'POST'])
@admin_required
def hero_image():
    current_url = SiteSetting.get('hero_image_url', '')

    if request.method == 'POST':
        action = request.form.get('action', 'upload')

        if action == 'remove':
            SiteSetting.set('hero_image_url', '')
            flash('Imagen del hero eliminada.', 'success')
            return redirect(url_for('admin.hero_image'))

        if action == 'url':
            url = request.form.get('image_url', '').strip()
            if url and _is_safe_image_url(url):
                SiteSetting.set('hero_image_url', url)
                flash('URL de imagen guardada correctamente.', 'success')
            else:
                flash('URL inválida o no permitida.', 'danger')
            return redirect(url_for('admin.hero_image'))

        # action == 'upload'
        file = request.files.get('image_file')
        filename = _save_image(file)
        if filename:
            SiteSetting.set('hero_image_url', f'/static/uploads/{filename}')
            flash('Imagen subida y guardada correctamente.', 'success')
        else:
            flash('Archivo inválido. Usá JPG, PNG o WebP.', 'danger')
        return redirect(url_for('admin.hero_image'))

    return render_template('admin/hero_image.html',
                           active_page='hero_image',
                           current_url=current_url)


def _is_safe_image_url(url):
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    blocked = {'localhost', '127.0.0.1', '0.0.0.0', '169.254.169.254'}
    if parsed.hostname in blocked or parsed.hostname.startswith('192.168.') or parsed.hostname.startswith('10.'):
        return False
    if not parsed.path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.svg')):
        return False
    return True


# ──────────────────── Andreani Test ────────────────────

def _andreani_payload_from_form(form_data):
    return {
        'contrato': form_data.get('contrato', '').strip(),
        'tipoDeServicio': form_data.get('tipo_servicio', 'estandar').strip(),
        'sucursalClienteID': int(form_data.get('sucursal_cliente_id', 0) or 0),
        'origen': {
            'postal': {
                'codigoPostal': form_data.get('origen_cp', '').strip(),
                'calle': form_data.get('origen_calle', '').strip(),
                'numero': form_data.get('origen_numero', '').strip(),
                'piso': form_data.get('origen_piso', '').strip(),
                'departamento': form_data.get('origen_depto', '').strip(),
                'localidad': form_data.get('origen_localidad', '').strip(),
                'region': form_data.get('origen_region', '').strip(),
                'pais': form_data.get('origen_pais', 'AR').strip(),
                'casillaDeCorreo': '',
                'componentesDeDireccion': [
                    {'meta': 'referencia', 'contenido': form_data.get('origen_ref', '').strip()}
                ],
            },
            'coordenadas': {
                'elevacion': 0,
                'latitud': float(form_data.get('origen_lat', 0) or 0),
                'longitud': float(form_data.get('origen_lng', 0) or 0),
                'poligono': 0,
            },
        },
        'destino': {
            'postal': {
                'codigoPostal': form_data.get('destino_cp', '').strip(),
                'calle': form_data.get('destino_calle', '').strip(),
                'numero': form_data.get('destino_numero', '').strip(),
                'piso': form_data.get('destino_piso', '').strip(),
                'departamento': form_data.get('destino_depto', '').strip(),
                'localidad': form_data.get('destino_localidad', '').strip(),
                'region': form_data.get('destino_region', '').strip(),
                'pais': form_data.get('destino_pais', 'AR').strip(),
                'casillaDeCorreo': '',
                'componentesDeDireccion': [
                    {'meta': 'referencia', 'contenido': form_data.get('destino_ref', '').strip()}
                ],
            },
            'coordenadas': {
                'elevacion': 0,
                'latitud': float(form_data.get('destino_lat', 0) or 0),
                'longitud': float(form_data.get('destino_lng', 0) or 0),
                'poligono': 0,
            },
        },
        'idPedido': form_data.get('id_pedido', '').strip(),
        'remitente': {
            'nombreCompleto': form_data.get('remitente_nombre', '').strip(),
            'email': form_data.get('remitente_email', '').strip(),
            'documentoTipo': form_data.get('remitente_doc_tipo', 'CUIT').strip(),
            'documentoNumero': form_data.get('remitente_doc_numero', '').strip(),
            'telefonos': [
                {'tipo': 1, 'numero': form_data.get('remitente_telefono', '').strip()}
            ],
        },
        'destinatario': [{
            'nombreCompleto': form_data.get('dest_nombre', '').strip(),
            'email': form_data.get('dest_email', '').strip(),
            'documentoTipo': form_data.get('dest_doc_tipo', 'DNI').strip(),
            'documentoNumero': form_data.get('dest_doc_numero', '').strip(),
            'telefonos': [
                {'tipo': 1, 'numero': form_data.get('dest_telefono', '').strip()}
            ],
        }],
        'remito': {
            'numeroRemito': form_data.get('numero_remito', '').strip(),
            'complementarios': [form_data.get('remito_complemento', '').strip()],
        },
        'centroDeCostos': form_data.get('centro_costos', 'ECOMMERCE').strip(),
        'productoAEntregar': form_data.get('producto', '').strip(),
        'tipoProducto': form_data.get('tipo_producto', 'PAQUETE').strip(),
        'categoriaFacturacion': form_data.get('categoria_facturacion', 'NORMAL').strip(),
        'pagoDestino': int(form_data.get('pago_destino', 0) or 0),
        'valorACobrar': float(form_data.get('valor_cobrar', 0) or 0),
        'fechaDeEntrega': {
            'fecha': form_data.get('fecha_entrega', '').strip(),
            'horaDesde': form_data.get('hora_desde', '09:00').strip(),
            'horaHasta': form_data.get('hora_hasta', '18:00').strip(),
        },
        'codigoVerificadorDeEntrega': form_data.get('codigo_verificador', '').strip(),
        'bultos': [{
            'kilos': float(form_data.get('kilos', 1) or 1),
            'largoCm': int(form_data.get('largo', 20) or 20),
            'altoCm': int(form_data.get('alto', 20) or 20),
            'anchoCm': int(form_data.get('ancho', 20) or 20),
            'volumenCm': int(form_data.get('volumen', 8000) or 8000),
            'valorDeclaradoSinImpuestos': float(form_data.get('valor_sin_imp', 0) or 0),
            'valorDeclaradoConImpuestos': float(form_data.get('valor_con_imp', 0) or 0),
            'referencias': [
                {'meta': 'sku', 'contenido': form_data.get('sku_ref', '').strip()}
            ],
            'descripcion': form_data.get('descripcion_bulto', '').strip(),
            'valorDeclarado': float(form_data.get('valor_declarado', 0) or 0),
            'ean': form_data.get('ean', '').strip(),
        }],
        'pagoPendienteEnMostrador': bool(form_data.get('pago_pendiente_mostrador')),
    }


@admin_bp.route('/andreani-test', methods=['GET', 'POST'])
@admin_required
def andreani_test():
    defaults = {
        'api_url': 'https://apissandbox.andreani.com/beta/transporte-distribucion/ordenes-de-envio',
        'tracking_url_template': 'https://apissandbox.andreani.com/beta/transporte-distribucion/ordenes-de-envio/{numero}',
        'tracking_number': '',
        'contrato': 'CTR-TEST',
        'tipo_servicio': 'estandar',
        'sucursal_cliente_id': '1',
        'origen_cp': '1414',
        'origen_calle': 'Honduras',
        'origen_numero': '3872',
        'origen_localidad': 'CABA',
        'origen_region': 'Buenos Aires',
        'origen_pais': 'AR',
        'origen_ref': 'Deposito principal',
        'origen_lat': '-34.5895',
        'origen_lng': '-58.4284',
        'destino_cp': '5000',
        'destino_calle': 'San Martin',
        'destino_numero': '1234',
        'destino_localidad': 'Cordoba',
        'destino_region': 'Cordoba',
        'destino_pais': 'AR',
        'destino_ref': 'Casa con porton negro',
        'destino_lat': '-31.4201',
        'destino_lng': '-64.1888',
        'id_pedido': f'ORD-WEB-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
        'remitente_nombre': 'UrbanPlast',
        'remitente_email': 'logistica@urbanplast.com',
        'remitente_doc_tipo': 'CUIT',
        'remitente_doc_numero': '30712345678',
        'remitente_telefono': '1144556677',
        'dest_nombre': 'Cliente Test',
        'dest_email': 'cliente@test.com',
        'dest_doc_tipo': 'DNI',
        'dest_doc_numero': '32123456',
        'dest_telefono': '1133344455',
        'numero_remito': f'REM-{datetime.utcnow().strftime("%H%M%S")}',
        'remito_complemento': 'WEB',
        'centro_costos': 'ECOMMERCE',
        'producto': 'Muebles de exterior',
        'tipo_producto': 'PAQUETE',
        'categoria_facturacion': 'NORMAL',
        'pago_destino': '0',
        'valor_cobrar': '0',
        'fecha_entrega': datetime.utcnow().strftime('%Y-%m-%d'),
        'hora_desde': '09:00',
        'hora_hasta': '18:00',
        'codigo_verificador': 'PIN1234',
        'kilos': '5',
        'largo': '60',
        'alto': '40',
        'ancho': '50',
        'volumen': '120000',
        'valor_sin_imp': '80000',
        'valor_con_imp': '96000',
        'valor_declarado': '96000',
        'sku_ref': 'SKU-TEST-001',
        'descripcion_bulto': 'Silla plastica apilable',
        'ean': '7791234567890',
        'pago_pendiente_mostrador': '',
    }

    form_data = dict(defaults)
    result = None

    if request.method == 'POST':
        form_data.update({k: v for k, v in request.form.items()})
        action = (form_data.get('action') or 'create_order').strip()
        api_key = (form_data.get('api_key') or '').strip() or current_app.config.get('ANDREANI_API_KEY', '')
        api_url = (form_data.get('api_url') or '').strip() or defaults['api_url']
        tracking_tpl = (form_data.get('tracking_url_template') or '').strip() or defaults['tracking_url_template']

        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': api_key,
            }

            if action == 'track_order':
                tracking_number = (form_data.get('tracking_number') or '').strip()
                if not tracking_number:
                    raise ValueError('Ingresa un numero de envio para consultar tracking.')
                tracking_url = tracking_tpl.replace('{numero}', tracking_number)
                response = requests.get(tracking_url, headers=headers, timeout=35, verify=True)
                payload = None
            else:
                payload = _andreani_payload_from_form(form_data)
                response = requests.post(api_url, headers=headers, json=payload, timeout=35, verify=True)

            try:
                response_body = response.json()
            except ValueError:
                response_body = response.text

            result = {
                'action': action,
                'status_code': response.status_code,
                'ok': response.ok,
                'payload': payload,
                'request_url': response.url,
                'response': response_body,
            }
        except Exception as exc:
            result = {
                'action': action,
                'status_code': None,
                'ok': False,
                'payload': None,
                'request_url': None,
                'response': f'Error ejecutando request: {exc}',
            }

    return render_template('admin/andreani_test_form.html', form_data=form_data, result=result)