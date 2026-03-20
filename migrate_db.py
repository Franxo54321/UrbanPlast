"""
Script para migrar la base de datos PostgreSQL en Railway.
Agrega las nuevas tablas (materials, colors, product_colors, product_images)
y la columna material_id a products.
"""
from app import create_app, db
from sqlalchemy import text

app = create_app()

MIGRATION_SQL = [
    # 1. Tabla materials
    """
    CREATE TABLE IF NOT EXISTS materials (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL
    );
    """,
    # 2. Tabla colors
    """
    CREATE TABLE IF NOT EXISTS colors (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        hex_code VARCHAR(7) NOT NULL DEFAULT '#000000'
    );
    """,
    # 3. Tabla product_colors (many-to-many)
    """
    CREATE TABLE IF NOT EXISTS product_colors (
        product_id INTEGER NOT NULL REFERENCES products(id),
        color_id INTEGER NOT NULL REFERENCES colors(id),
        PRIMARY KEY (product_id, color_id)
    );
    """,
    # 4. Tabla product_images
    """
    CREATE TABLE IF NOT EXISTS product_images (
        id SERIAL PRIMARY KEY,
        product_id INTEGER NOT NULL REFERENCES products(id),
        filename VARCHAR(300) NOT NULL,
        position INTEGER DEFAULT 0
    );
    """,
    # 5. Columna material_id en products (nullable, sin FK todavía)
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
    # 6. FK para material_id
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
    # 7. Insertar materiales por defecto
    """
    INSERT INTO materials (name) VALUES ('Plástico')
    ON CONFLICT (name) DO NOTHING;
    """,
    """
    INSERT INTO materials (name) VALUES ('Madera')
    ON CONFLICT (name) DO NOTHING;
    """,
    # 8. Migrar datos existentes: asignar material_id según campo material
    """
    UPDATE products SET material_id = (SELECT id FROM materials WHERE name = 'Plástico')
    WHERE material = 'plastico' AND material_id IS NULL;
    """,
    """
    UPDATE products SET material_id = (SELECT id FROM materials WHERE name = 'Madera')
    WHERE material = 'madera' AND material_id IS NULL;
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
