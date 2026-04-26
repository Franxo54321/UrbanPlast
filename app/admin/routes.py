import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
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
    except Exception:
        return None

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
    with open(filepath, 'wb') as out:
        out.write(file_bytes)
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
                    path = os.path.join(current_app.config['UPLOAD_FOLDER'], img.filename)
                    if os.path.exists(path):
                        os.remove(path)
                    db.session.delete(img)

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
            if url:
                SiteSetting.set('hero_image_url', url)
                flash('URL de imagen guardada correctamente.', 'success')
            else:
                flash('La URL no puede estar vacía.', 'danger')
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
