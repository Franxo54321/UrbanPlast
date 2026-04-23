"""
Script para migrar la base de datos PostgreSQL en Railway.
Crea/actualiza todas las tablas necesarias de forma segura (idempotente).
"""
from app import create_app, db
from sqlalchemy import text

app = create_app()

MIGRATION_SQL = [
    # ── Tablas originales ──────────────────────────────────────────────────────

    """
    CREATE TABLE IF NOT EXISTS materials (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS colors (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        hex_code VARCHAR(7) NOT NULL DEFAULT '#000000'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS product_colors (
        product_id INTEGER NOT NULL REFERENCES products(id),
        color_id INTEGER NOT NULL REFERENCES colors(id),
        PRIMARY KEY (product_id, color_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS product_images (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL REFERENCES products(id),
        filename VARCHAR(300) NOT NULL,
        position INTEGER DEFAULT 0
    );
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='products' AND column_name='material_id'
        ) THEN
            ALTER TABLE products ADD COLUMN material_id INTEGER;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name='fk_products_material_id' AND table_name='products'
        ) THEN
            ALTER TABLE products
            ADD CONSTRAINT fk_products_material_id
            FOREIGN KEY (material_id) REFERENCES materials(id);
        END IF;
    END $$;
    """,
    """
    INSERT INTO materials (name) VALUES ('Plástico') ON CONFLICT (name) DO NOTHING;
    """,
    """
    INSERT INTO materials (name) VALUES ('Madera') ON CONFLICT (name) DO NOTHING;
    """,
    """
    UPDATE products SET material_id = (SELECT id FROM materials WHERE name = 'Plástico')
    WHERE material = 'plastico' AND material_id IS NULL;
    """,
    """
    UPDATE products SET material_id = (SELECT id FROM materials WHERE name = 'Madera')
    WHERE material = 'madera' AND material_id IS NULL;
    """,

    # ── Nuevas tablas (mejoras v2) ─────────────────────────────────────────────

    # Cupones
    """
    CREATE TABLE IF NOT EXISTS coupons (
        id SERIAL PRIMARY KEY,
        code VARCHAR(50) UNIQUE NOT NULL,
        discount_type VARCHAR(10) NOT NULL,
        discount_value NUMERIC(10,2) NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        uses_left INTEGER,
        min_order NUMERIC(10,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_coupons_code ON coupons(code);
    """,

    # Reseñas
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        rating INTEGER NOT NULL,
        comment TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews(user_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_reviews_product_id ON reviews(product_id);
    """,

    # Wishlist
    """
    CREATE TABLE IF NOT EXISTS wishlist (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_wishlist_user_product UNIQUE (user_id, product_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_wishlist_user_id ON wishlist(user_id);
    """,

    # Historial de estados de pedidos
    """
    CREATE TABLE IF NOT EXISTS order_status_history (
        id SERIAL PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        status VARCHAR(30) NOT NULL,
        note VARCHAR(200),
        changed_at TIMESTAMP DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_order_status_history_order_id ON order_status_history(order_id);
    """,

    # ── Verificación de email en users ────────────────────────────────────────

    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='users' AND column_name='email_verified'
        ) THEN
            ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='users' AND column_name='verification_token'
        ) THEN
            ALTER TABLE users ADD COLUMN verification_token VARCHAR(100);
        END IF;
    END $$;
    """,
    # El admin ya existe, marcarlo como verificado
    """
    UPDATE users SET email_verified = TRUE WHERE is_admin = TRUE;
    """,

    # ── Nuevas columnas en orders ──────────────────────────────────────────────

    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='orders' AND column_name='tracking_number'
        ) THEN
            ALTER TABLE orders ADD COLUMN tracking_number VARCHAR(100);
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='orders' AND column_name='discount_amount'
        ) THEN
            ALTER TABLE orders ADD COLUMN discount_amount NUMERIC(10,2) DEFAULT 0;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='orders' AND column_name='coupon_id'
        ) THEN
            ALTER TABLE orders ADD COLUMN coupon_id INTEGER REFERENCES coupons(id);
        END IF;
    END $$;
    """,
]

with app.app_context():
    print("Iniciando migración...")
    for i, sql in enumerate(MIGRATION_SQL, 1):
        try:
            db.session.execute(text(sql))
            db.session.commit()
            print(f"  Paso {i}/{len(MIGRATION_SQL)}: OK")
        except Exception as e:
            db.session.rollback()
            print(f"  Paso {i}/{len(MIGRATION_SQL)}: {e}")
    print("Migración completada.")
