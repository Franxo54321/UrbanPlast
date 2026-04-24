from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    products = db.relationship('Product', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Material(db.Model):
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<Material {self.name}>'


class Color(db.Model):
    __tablename__ = 'colors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    hex_code = db.Column(db.String(7), nullable=False, default='#000000')

    def __repr__(self):
        return f'<Color {self.name}>'


product_colors = db.Table('product_colors',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('color_id', db.Integer, db.ForeignKey('colors.id'), primary_key=True)
)


class ProductImage(db.Model):
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    position = db.Column(db.Integer, default=0)

    @property
    def url(self):
        return f'/static/uploads/{self.filename}'


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    material = db.Column(db.String(50))
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=True)
    image = db.Column(db.String(300))
    featured = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    material_rel = db.relationship('Material', backref=db.backref('products', lazy='dynamic'))
    colors = db.relationship('Color', secondary=product_colors, backref=db.backref('products', lazy='dynamic'))
    images = db.relationship('ProductImage', backref='product', lazy='dynamic',
                             cascade='all, delete-orphan', order_by='ProductImage.position')

    def __repr__(self):
        return f'<Product {self.name}>'

    @property
    def material_name(self):
        if self.material_rel:
            return self.material_rel.name
        return self.material or ''

    @property
    def image_url(self):
        first = self.images.first()
        if first:
            return first.url
        if self.image:
            return f'/static/uploads/{self.image}'
        return '/static/img/no-image.svg'

    @property
    def all_image_urls(self):
        imgs = self.images.order_by(ProductImage.position).all()
        if imgs:
            return [img.url for img in imgs]
        if self.image:
            return [f'/static/uploads/{self.image}']
        return ['/static/img/no-image.svg']

    @property
    def avg_rating(self):
        reviews = self.reviews.all()
        if not reviews:
            return None
        return round(sum(r.rating for r in reviews) / len(reviews), 1)

    @property
    def review_count(self):
        return self.reviews.count()


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('reviews', lazy='dynamic'))
    product = db.relationship('Product', backref=db.backref('reviews', lazy='dynamic'))

    def __repr__(self):
        return f'<Review {self.id} rating={self.rating}>'


class Wishlist(db.Model):
    __tablename__ = 'wishlist'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='uq_wishlist_user_product'),)

    user = db.relationship('User', backref=db.backref('wishlist_items', lazy='dynamic'))
    product = db.relationship('Product', backref='wishlist_items')


class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(10), nullable=False)  # 'percent' or 'fixed'
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    active = db.Column(db.Boolean, default=True)
    uses_left = db.Column(db.Integer, nullable=True)  # None = unlimited
    min_order = db.Column(db.Numeric(10, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def compute_discount(self, total):
        total = float(total)
        val = float(self.discount_value)
        if self.discount_type == 'percent':
            return round(min(total * val / 100, total), 2)
        return round(min(val, total), 2)

    def __repr__(self):
        return f'<Coupon {self.code}>'


class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('cart_items', lazy='dynamic'))
    product = db.relationship('Product', backref='cart_items')

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=True)
    payment_method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), default='pendiente')
    delivery_type = db.Column(db.String(20), default='envio')
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    province = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(100), default='Argentina')
    phone = db.Column(db.String(50))
    notes = db.Column(db.Text)
    tracking_number = db.Column(db.String(100))
    mp_preference_id = db.Column(db.String(200))
    mp_payment_id = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('orders', lazy='dynamic'))
    coupon = db.relationship('Coupon', backref='orders')
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    status_history = db.relationship('OrderStatusHistory', backref='order', lazy='dynamic',
                                     order_by='OrderStatusHistory.changed_at',
                                     cascade='all, delete-orphan')

    @property
    def full_address(self):
        parts = [self.address, self.city, self.province]
        if self.postal_code:
            parts.append(self.postal_code)
        parts.append(self.country or 'Argentina')
        return ', '.join(p for p in parts if p)


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    product = db.relationship('Product')

    @property
    def subtotal(self):
        return self.price * self.quantity


class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.String(200))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<OrderStatusHistory order={self.order_id} status={self.status}>'
