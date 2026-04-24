from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Product, Category, Material, Review, Wishlist, OrderItem, Order

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/')
def index():
    featured = Product.query.filter_by(featured=True, active=True).limit(8).all()
    latest = Product.query.filter_by(active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.all()
    materials = Material.query.order_by(Material.name).all()
    return render_template('index.html', featured=featured, latest=latest,
                           categories=categories, materials=materials)


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


@main_bp.route('/api/categorias')
def api_categories():
    categories = Category.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'product_count': c.products.filter_by(active=True).count()
    } for c in categories])
