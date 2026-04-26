from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Product, Category, Material, Review, Wishlist, OrderItem, Order, SiteSetting
import requests

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/')
def index():
    featured = Product.query.filter_by(featured=True, active=True).limit(8).all()
    latest = Product.query.filter_by(active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.all()
    materials = Material.query.order_by(Material.name).all()
    hero_image_url = SiteSetting.get('hero_image_url', '')
    return render_template('index.html', featured=featured, latest=latest,
                           categories=categories, materials=materials,
                           hero_image_url=hero_image_url)


@main_bp.route('/nosotros')
def about():
    return render_template('about.html')


@main_bp.route('/contacto', methods=['GET', 'POST'])
def contact():
    from app.main.forms import ContactForm
    form = ContactForm()
    if form.validate_on_submit():
        _send_contact_email(form.name.data, form.email.data,
                            form.subject.data, form.message.data)
        flash('¡Mensaje enviado! Te responderemos a la brevedad.', 'success')
        return redirect(url_for('main.contact'))
    return render_template('contact.html', form=form)


def _send_contact_email(name, email, subject, message):
    try:
        from app.email_utils import send_email, is_email_configured
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if not admin_email or not is_email_configured():
            return
        body = render_template('emails/contact_notification.html',
                               name=name, email=email,
                               subject=subject, message=message,
                               now=datetime.utcnow())
        send_email(
            subject=f'[UrbanPlast] Contacto: {subject}',
            recipients=[admin_email],
            html=body,
            reply_to=email
        )
    except Exception:
        pass


@main_bp.route('/productos')
def products():
    page = request.args.get('page', 1, type=int)
    category_slug = request.args.get('categoria')
    material_id = request.args.get('material', type=int)
    q = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    sort = request.args.get('sort', 'nuevo')

    query = Product.query.filter_by(active=True)

    if q:
        like = f'%{q}%'
        query = query.filter(Product.name.ilike(like) | Product.description.ilike(like))

    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first_or_404()
        query = query.filter_by(category_id=cat.id)

    if material_id:
        query = query.filter_by(material_id=material_id)

    if min_price is not None:
        query = query.filter(Product.price >= min_price)

    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if sort == 'precio_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'precio_desc':
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=12)
    categories = Category.query.all()
    materials = Material.query.order_by(Material.name).all()

    wishlist_ids = set()
    if current_user.is_authenticated:
        wishlist_ids = {w.product_id for w in
                        Wishlist.query.filter_by(user_id=current_user.id).all()}

    return render_template('products.html',
                           products=products,
                           categories=categories,
                           current_category=category_slug,
                           current_material=material_id,
                           materials=materials,
                           q=q,
                           min_price=min_price,
                           max_price=max_price,
                           sort=sort,
                           wishlist_ids=wishlist_ids)


@main_bp.route('/producto/<slug>')
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.active == True
    ).limit(4).all()

    reviews = product.reviews.order_by(Review.created_at.desc()).all()

    user_reviewed = False
    user_purchased = False
    in_wishlist = False

    if current_user.is_authenticated:
        user_reviewed = Review.query.filter_by(
            user_id=current_user.id, product_id=product.id).first() is not None

        user_purchased = db.session.query(OrderItem).join(Order).filter(
            OrderItem.product_id == product.id,
            Order.user_id == current_user.id,
            Order.status != 'cancelado'
        ).first() is not None

        in_wishlist = Wishlist.query.filter_by(
            user_id=current_user.id, product_id=product.id).first() is not None

    return render_template('product_detail.html',
                           product=product,
                           related=related,
                           reviews=reviews,
                           user_reviewed=user_reviewed,
                           user_purchased=user_purchased,
                           in_wishlist=in_wishlist)


@main_bp.route('/producto/<slug>/resena', methods=['POST'])
@login_required
def add_review(slug):
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()

    if Review.query.filter_by(user_id=current_user.id, product_id=product.id).first():
        flash('Ya dejaste una reseña para este producto.', 'warning')
        return redirect(url_for('main.product_detail', slug=slug))

    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or not (1 <= rating <= 5):
        flash('Calificación inválida.', 'danger')
        return redirect(url_for('main.product_detail', slug=slug))

    db.session.add(Review(
        user_id=current_user.id,
        product_id=product.id,
        rating=rating,
        comment=comment or None
    ))
    db.session.commit()
    flash('¡Gracias por tu reseña!', 'success')
    return redirect(url_for('main.product_detail', slug=slug))


@main_bp.route('/favoritos/toggle/<int:product_id>', methods=['POST'])
@login_required
def wishlist_toggle(product_id):
    product = Product.query.get_or_404(product_id)
    item = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'in_wishlist': False, 'message': 'Eliminado de favoritos'})
    db.session.add(Wishlist(user_id=current_user.id, product_id=product_id))
    db.session.commit()
    return jsonify({'in_wishlist': True, 'message': 'Agregado a favoritos'})


@main_bp.route('/mis-favoritos')
@login_required
def wishlist():
    items = Wishlist.query.filter_by(user_id=current_user.id)\
                          .order_by(Wishlist.created_at.desc()).all()
    return render_template('wishlist.html', items=items)


@main_bp.route('/api/productos')
def api_products():
    category_slug = request.args.get('categoria')
    material_id = request.args.get('material', type=int)

    query = Product.query.filter_by(active=True)

    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    if material_id:
        query = query.filter_by(material_id=material_id)

    products = query.order_by(Product.created_at.desc()).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'slug': p.slug,
        'price': str(p.price),
        'material': p.material_name,
        'image_url': p.image_url,
        'category': p.category.name
    } for p in products])


@main_bp.route('/api/buscar')
def search_suggestions():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    results = Product.query.filter(
        Product.active == True,
        db.or_(Product.name.ilike(like), Product.description.ilike(like))
    ).limit(6).all()
    return jsonify([{
        'name': p.name,
        'slug': p.slug,
        'price': f'${float(p.price):.2f}',
        'image': p.image_url,
        'category': p.category.name
    } for p in results])


@main_bp.route('/api/categorias')
def api_categories():
    categories = Category.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'product_count': c.products.filter_by(active=True).count()
    } for c in categories])


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


@main_bp.route('/admin/andreani-test', methods=['GET', 'POST'])
@login_required
def andreani_test():
    if not current_user.is_admin:
        flash('Solo administradores pueden acceder a esta pantalla.', 'danger')
        return redirect(url_for('main.index'))

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
                response = requests.get(tracking_url, headers=headers, timeout=35)
                payload = None
            else:
                payload = _andreani_payload_from_form(form_data)
                response = requests.post(api_url, headers=headers, json=payload, timeout=35)

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
