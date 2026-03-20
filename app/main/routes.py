from flask import Blueprint, render_template, request, jsonify
from app.models import Product, Category, Material

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/')
def index():
    featured = Product.query.filter_by(featured=True, active=True).limit(8).all()
    latest = Product.query.filter_by(active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.all()
    materials = Material.query.order_by(Material.name).all()
    return render_template('index.html', featured=featured, latest=latest, categories=categories, materials=materials)


@main_bp.route('/nosotros')
def about():
    return render_template('about.html')


@main_bp.route('/contacto')
def contact():
    return render_template('contact.html')


@main_bp.route('/productos')
def products():
    page = request.args.get('page', 1, type=int)
    category_slug = request.args.get('categoria')
    material_id = request.args.get('material', type=int)

    query = Product.query.filter_by(active=True)

    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first_or_404()
        query = query.filter_by(category_id=cat.id)

    if material_id:
        query = query.filter_by(material_id=material_id)

    products = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=12)
    categories = Category.query.all()
    materials = Material.query.order_by(Material.name).all()
    return render_template('products.html', products=products, categories=categories,
                           current_category=category_slug, current_material=material_id, materials=materials)


@main_bp.route('/producto/<slug>')
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.active == True
    ).limit(4).all()
    return render_template('product_detail.html', product=product, related=related)


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
