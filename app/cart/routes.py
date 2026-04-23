import hmac
import hashlib
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import Product, CartItem, Order, OrderItem
from app.auth.forms import CheckoutForm

cart_bp = Blueprint('cart', __name__, template_folder='templates')


def _cart_count(user_id):
    return db.session.query(func.sum(CartItem.quantity)).filter_by(user_id=user_id).scalar() or 0


@cart_bp.route('/')
@login_required
def view_cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.subtotal for item in items)
    return render_template('cart.html', items=items, total=total)


@cart_bp.route('/agregar', methods=['POST'])
@login_required
def add_to_cart():
    data = request.get_json()
    if not data or 'product_id' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    product_id = data['product_id']
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'error': 'Cantidad inválida'}), 400

    product = Product.query.get(product_id)
    if not product or not product.active:
        return jsonify({'error': 'Producto no encontrado'}), 404

    item = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    new_quantity = (item.quantity if item else 0) + quantity
    if product.stock < new_quantity:
        return jsonify({'error': 'Stock insuficiente'}), 400

    if item:
        item.quantity = new_quantity
    else:
        item = CartItem(user_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

    db.session.commit()
    return jsonify({'success': True, 'cart_count': _cart_count(current_user.id), 'message': 'Producto agregado al carrito'})


@cart_bp.route('/actualizar', methods=['POST'])
@login_required
def update_cart():
    data = request.get_json()
    if not data or 'item_id' not in data or 'quantity' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    quantity = data['quantity']
    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'error': 'Cantidad inválida'}), 400

    item = CartItem.query.filter_by(id=data['item_id'], user_id=current_user.id).first()
    if not item:
        return jsonify({'error': 'Item no encontrado'}), 404

    if item.product.stock < quantity:
        return jsonify({'error': 'Stock insuficiente'}), 400

    item.quantity = quantity
    db.session.commit()

    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(i.subtotal for i in items)

    return jsonify({
        'success': True,
        'subtotal': str(item.subtotal),
        'total': str(total),
        'cart_count': _cart_count(current_user.id)
    })


@cart_bp.route('/eliminar', methods=['POST'])
@login_required
def remove_from_cart():
    data = request.get_json()
    if not data or 'item_id' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    item = CartItem.query.filter_by(id=data['item_id'], user_id=current_user.id).first()
    if not item:
        return jsonify({'error': 'Item no encontrado'}), 404

    db.session.delete(item)
    db.session.commit()

    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(i.subtotal for i in items)

    return jsonify({'success': True, 'total': str(total), 'cart_count': _cart_count(current_user.id)})


@cart_bp.route('/count')
@login_required
def cart_count():
    return jsonify({'count': _cart_count(current_user.id)})


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash('Tu carrito está vacío.', 'warning')
        return redirect(url_for('main.products'))

    total = sum(item.subtotal for item in items)
    form = CheckoutForm()

    if form.validate_on_submit():
        order = Order(
            user_id=current_user.id,
            total=total,
            payment_method=form.payment_method.data,
            delivery_type=form.delivery_type.data,
            address=form.address.data,
            city=form.city.data,
            province=form.province.data,
            postal_code=form.postal_code.data,
            country=form.country.data or 'Argentina',
            phone=form.phone.data,
            notes=form.notes.data,
            status='pendiente'
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                product_name=item.product.name,
                price=item.product.price,
                quantity=item.quantity
            )
            db.session.add(order_item)

        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        # Si eligió MercadoPago, crear preferencia y redirigir
        if form.payment_method.data == 'mercadopago':
            mp_url = _create_mp_preference(order)
            if mp_url:
                return redirect(mp_url)

        flash('¡Pedido realizado con éxito!', 'success')
        return redirect(url_for('cart.order_detail', order_id=order.id))

    return render_template('checkout.html', form=form, items=items, total=total)


def _create_mp_preference(order):
    """Crea una preferencia de pago en MercadoPago y retorna la URL de pago."""
    access_token = current_app.config.get('MP_ACCESS_TOKEN', '')
    if not access_token:
        flash('MercadoPago no está configurado. Contactanos para completar el pago.', 'warning')
        return None

    import mercadopago
    sdk = mercadopago.SDK(access_token)

    items_mp = []
    for item in order.items:
        items_mp.append({
            "title": item.product_name,
            "quantity": item.quantity,
            "unit_price": float(item.price),
            "currency_id": "ARS",
        })

    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    # Railway provee el dominio sin esquema; aseguramos https en producción
    if base_url and not base_url.startswith('http'):
        base_url = 'https://' + base_url

    preference_data = {
        "items": items_mp,
        "payer": {
            "email": order.user.email,
        },
        "back_urls": {
            "success": f"{base_url}/cart/mp/success?order_id={order.id}",
            "failure": f"{base_url}/cart/mp/failure?order_id={order.id}",
            "pending": f"{base_url}/cart/mp/pending?order_id={order.id}",
        },
        "auto_return": "approved",
        "external_reference": str(order.id),
        "notification_url": f"{base_url}/cart/mp/webhook",
    }

    result = sdk.preference().create(preference_data)
    preference = result.get("response", {})

    if preference.get("id"):
        order.mp_preference_id = preference["id"]
        db.session.commit()
        return preference.get("init_point", "")

    return None


def _verify_mp_webhook(req):
    """Verify MercadoPago webhook signature using HMAC-SHA256.
    Only enforced when MP_WEBHOOK_SECRET is set in config."""
    secret = current_app.config.get('MP_WEBHOOK_SECRET', '')
    if not secret:
        return True

    x_signature = req.headers.get('x-signature', '')
    x_request_id = req.headers.get('x-request-id', '')
    if not x_signature:
        return False

    ts = v1 = None
    for part in x_signature.split(','):
        key, _, value = part.partition('=')
        if key.strip() == 'ts':
            ts = value.strip()
        elif key.strip() == 'v1':
            v1 = value.strip()

    if not ts or not v1:
        return False

    data = req.get_json(silent=True) or {}
    data_id = str(data.get('data', {}).get('id', ''))
    template = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    expected = hmac.new(secret.encode(), template.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@cart_bp.route('/mp/success')
@login_required
def mp_success():
    order_id = request.args.get('order_id', type=int)
    payment_id = request.args.get('payment_id', '')
    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
        if order:
            order.status = 'pagado'
            order.mp_payment_id = str(payment_id)
            db.session.commit()
    flash('¡Pago aprobado! Tu pedido fue confirmado.', 'success')
    return redirect(url_for('cart.order_detail', order_id=order_id))


@cart_bp.route('/mp/failure')
@login_required
def mp_failure():
    order_id = request.args.get('order_id', type=int)
    flash('El pago fue rechazado. Podés intentar de nuevo o elegir otro método.', 'danger')
    return redirect(url_for('cart.order_detail', order_id=order_id))


@cart_bp.route('/mp/pending')
@login_required
def mp_pending():
    order_id = request.args.get('order_id', type=int)
    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
        if order:
            order.mp_payment_id = str(request.args.get('payment_id', ''))
            db.session.commit()
    flash('Tu pago está pendiente de acreditación.', 'info')
    return redirect(url_for('cart.order_detail', order_id=order_id))


@cart_bp.route('/mp/webhook', methods=['POST'])
def mp_webhook():
    """Webhook de MercadoPago para notificaciones de pago (IPN)."""
    if not _verify_mp_webhook(request):
        return jsonify({'status': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    if data.get('type') == 'payment':
        access_token = current_app.config.get('MP_ACCESS_TOKEN', '')
        if not access_token:
            return jsonify({'status': 'no_config'}), 200

        import mercadopago
        sdk = mercadopago.SDK(access_token)
        payment_id = data.get('data', {}).get('id')
        if payment_id:
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get('response', {})
            ext_ref = payment.get('external_reference', '')
            status = payment.get('status', '')

            if ext_ref:
                order = Order.query.get(int(ext_ref))
                if order:
                    order.mp_payment_id = str(payment_id)
                    if status == 'approved':
                        order.status = 'pagado'
                    elif status in ('pending', 'in_process'):
                        order.status = 'pendiente'
                    elif status in ('rejected', 'cancelled'):
                        order.status = 'cancelado'
                    db.session.commit()

    return jsonify({'status': 'ok'}), 200


@cart_bp.route('/pedido/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('order_detail.html', order=order)


@cart_bp.route('/mis-pedidos')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)
