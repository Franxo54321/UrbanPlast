document.addEventListener('DOMContentLoaded', function () {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    // --- Update cart badge ---
    function updateCartBadge(count) {
        const badge = document.getElementById('cartBadge');
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    // Fetch cart count on load
    fetch('/cart/count')
        .then(r => { if (r.ok) return r.json(); throw r; })
        .then(data => updateCartBadge(data.count))
        .catch(() => {});

    // --- Toast ---
    function showToast(message, type) {
        const toastEl = document.getElementById('toastNotif');
        const toastMsg = document.getElementById('toastMsg');
        if (!toastEl) return;
        toastEl.className = 'toast align-items-center border-0 text-bg-' + (type || 'success');
        toastMsg.textContent = message;
        const toast = new bootstrap.Toast(toastEl, { delay: 2500 });
        toast.show();
    }

    // --- Add to cart (listing pages) ---
    document.querySelectorAll('.add-to-cart-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const productId = this.dataset.productId;
            addToCart(productId, 1);
        });
    });

    // --- Global addToCart function ---
    window.addToCart = function (productId, quantity) {
        fetch('/cart/agregar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ product_id: parseInt(productId), quantity: quantity || 1 })
        })
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/auth/login';
                return;
            }
            return response.json();
        })
        .then(function (data) {
            if (!data) return;
            if (data.success) {
                updateCartBadge(data.cart_count);
                showToast(data.message || 'Producto agregado al carrito', 'success');
            } else {
                showToast(data.error || 'Error al agregar', 'danger');
            }
        })
        .catch(function () {
            showToast('Error de conexión', 'danger');
        });
    };

    // --- Cart page: quantity buttons ---
    document.querySelectorAll('.cart-qty-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const itemId = this.dataset.itemId;
            const input = document.querySelector('.cart-qty-input[data-item-id="' + itemId + '"]');
            let val = parseInt(input.value) || 1;
            if (this.dataset.action === 'plus') val++;
            else if (this.dataset.action === 'minus' && val > 1) val--;
            input.value = val;
            updateCartItem(itemId, val);
        });
    });

    document.querySelectorAll('.cart-qty-input').forEach(function (input) {
        input.addEventListener('change', function () {
            const val = Math.max(1, parseInt(this.value) || 1);
            this.value = val;
            updateCartItem(this.dataset.itemId, val);
        });
    });

    function updateCartItem(itemId, quantity) {
        fetch('/cart/actualizar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ item_id: parseInt(itemId), quantity: quantity })
        })
        .then(r => r.json())
        .then(function (data) {
            if (data.success) {
                const sub = document.getElementById('subtotal-' + itemId);
                if (sub) sub.textContent = '$' + parseFloat(data.subtotal).toFixed(2);
                const tot = document.getElementById('cartTotal');
                if (tot) tot.textContent = '$' + parseFloat(data.total).toFixed(2);
                updateCartBadge(data.cart_count);
            }
        })
        .catch(function () {
            showToast('Error al actualizar', 'danger');
        });
    }

    // --- Cart page: remove item ---
    document.querySelectorAll('.cart-remove-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const itemId = this.dataset.itemId;
            fetch('/cart/eliminar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ item_id: parseInt(itemId) })
            })
            .then(r => r.json())
            .then(function (data) {
                if (data.success) {
                    const row = document.getElementById('cartRow-' + itemId);
                    if (row) row.remove();
                    const tot = document.getElementById('cartTotal');
                    if (tot) tot.textContent = '$' + parseFloat(data.total).toFixed(2);
                    updateCartBadge(data.cart_count);
                    showToast('Producto eliminado del carrito', 'info');
                    if (data.cart_count === 0) location.reload();
                }
            })
            .catch(function () {
                showToast('Error al eliminar', 'danger');
            });
        });
    });

    // --- Admin: delete product ---
    let deleteProductId = null;
    const deleteModal = document.getElementById('deleteModal');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

    document.querySelectorAll('.admin-delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            deleteProductId = this.dataset.productId;
            document.getElementById('deleteProductName').textContent = this.dataset.productName;
            new bootstrap.Modal(deleteModal).show();
        });
    });

    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', function () {
            if (!deleteProductId) return;
            fetch('/admin/productos/' + deleteProductId + '/eliminar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            })
            .then(r => r.json())
            .then(function (data) {
                if (data.success) {
                    const row = document.getElementById('adminRow-' + deleteProductId);
                    if (row) row.remove();
                    bootstrap.Modal.getInstance(deleteModal).hide();
                    showToast('Producto eliminado', 'success');
                }
            })
            .catch(function () {
                showToast('Error al eliminar', 'danger');
            });
        });
    }
});
