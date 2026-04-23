# MueblesPro - E-commerce de Muebles

Tienda online de muebles de plástico y madera. Hecha con Flask + PostgreSQL.

## Requisitos

- Python 3.10+
- PostgreSQL 14+

## Instalación local

```bash
# 1. Clonar y entrar al proyecto
cd Ecomerce-muebles

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
copy .env.example .env
# Editar .env con tus datos de PostgreSQL

# 5. Crear la base de datos en PostgreSQL
# psql -U postgres -c "CREATE DATABASE muebles_db;"

# 6. Ejecutar
python run.py
```

La app corre en `http://localhost:5000`

## Deploy con Gunicorn (Linux)

```bash
gunicorn wsgi:app -w 4 -b 0.0.0.0:8000
```

## Estructura

```
├── app/
│   ├── __init__.py          # Factory de la app
│   ├── models.py            # Modelos SQLAlchemy
│   ├── auth/                # Login / Register
│   ├── main/                # Páginas públicas
│   ├── admin/               # Panel de administración
│   ├── cart/                # Carrito (AJAX)
│   ├── static/              # CSS, JS, uploads
│   └── templates/           # HTML (Jinja2)
├── config.py
├── run.py                   # Servidor de desarrollo
├── wsgi.py                  # Entry point producción
└── requirements.txt
```

## Funcionalidades

- ✅ Catálogo de productos con filtros por categoría y material
- ✅ Carrusel de productos destacados en el inicio
- ✅ Dropdown de categorías en el header
- ✅ Carrito de compras con AJAX (sin recargar página)
- ✅ Login / Registro de usuarios
- ✅ Panel de admin (CRUD de productos, solo para administradores)
- ✅ Subida de imágenes
- ✅ Diseño responsive con Bootstrap 5
