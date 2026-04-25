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

    // --- Mini-carrito lateral ---
    const miniCartEl = document.getElementById('miniCart');
    if (miniCartEl) {
        miniCartEl.addEventListener('show.bs.offcanvas', loadMiniCart);
    }

    function loadMiniCart() {
        const loading = document.getElementById('miniCartLoading');
        const empty   = document.getElementById('miniCartEmpty');
        const itemsEl = document.getElementById('miniCartItems');
        const footer  = document.getElementById('miniCartFooter');
        if (!loading) return;

        loading.classList.remove('d-none');
        empty.classList.add('d-none');
        itemsEl.classList.add('d-none');
        footer.classList.add('d-none');

        fetch('/cart/items')
            .then(function (r) { if (r.ok) return r.json(); throw r; })
            .then(function (data) {
                loading.classList.add('d-none');
                if (!data.items || data.items.length === 0) {
                    empty.classList.remove('d-none');
                    return;
                }
                itemsEl.innerHTML = data.items.map(function (item) {
                    return '<div class="d-flex gap-2 py-2 border-bottom align-items-center" id="miniRow-' + item.id + '">' +
                        '<a href="/producto/' + item.slug + '" data-bs-dismiss="offcanvas">' +
                        '<img src="' + item.image + '" style="width:56px;height:56px;object-fit:cover;border-radius:6px;" alt="' + item.name + '" loading="lazy"></a>' +
                        '<div class="flex-grow-1 overflow-hidden">' +
                        '<a href="/producto/' + item.slug + '" class="text-decoration-none text-dark small fw-semibold d-block text-truncate" data-bs-dismiss="offcanvas">' + item.name + '</a>' +
                        '<small class="text-muted mc-unit-price" data-price="' + item.price + '">$' + item.price.toFixed(2) + ' c/u</small>' +
                        '<div class="d-flex align-items-center gap-1 mt-1">' +
                        '<button class="btn btn-outline-secondary btn-sm px-2 py-0 mc-qty" data-item-id="' + item.id + '" data-action="minus" style="line-height:1.6;">−</button>' +
                        '<span class="mx-1 small fw-semibold mc-qty-num" data-item-id="' + item.id + '">' + item.quantity + '</span>' +
                        '<button class="btn btn-outline-secondary btn-sm px-2 py-0 mc-qty" data-item-id="' + item.id + '" data-action="plus" style="line-height:1.6;">+</button>' +
                        '</div></div>' +
                        '<div class="text-end d-flex flex-column align-items-end gap-1">' +
                        '<span class="fw-bold small" id="miniSub-' + item.id + '">$' + item.subtotal.toFixed(2) + '</span>' +
                        '<button class="btn btn-link text-danger p-0 mc-remove" data-item-id="' + item.id + '" style="font-size:.85rem;"><i class="bi bi-trash3"></i></button>' +
                        '</div></div>';
                }).join('');

                document.getElementById('miniCartTotal').textContent = '$' + data.total.toFixed(2);
                itemsEl.classList.remove('d-none');
                footer.classList.remove('d-none');

                // Quantity buttons
                itemsEl.querySelectorAll('.mc-qty').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        const itemId = this.dataset.itemId;
                        const numEl  = itemsEl.querySelector('.mc-qty-num[data-item-id="' + itemId + '"]');
                        let qty = parseInt(numEl.textContent) || 1;
                        if (this.dataset.action === 'plus') qty++;
                        else if (qty > 1) qty--;
                        numEl.textContent = qty;
                        fetch('/cart/actualizar', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                            body: JSON.stringify({ item_id: parseInt(itemId), quantity: qty })
                        })
                        .then(function (r) { return r.json(); })
                        .then(function (res) {
                            if (res.success) {
                                const subEl = document.getElementById('miniSub-' + itemId);
                                if (subEl) subEl.textContent = '$' + parseFloat(res.subtotal).toFixed(2);
                                document.getElementById('miniCartTotal').textContent = '$' + parseFloat(res.total).toFixed(2);
                                updateCartBadge(res.cart_count);
                            }
                        });
                    });
                });

                // Remove buttons
                itemsEl.querySelectorAll('.mc-remove').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        const itemId = this.dataset.itemId;
                        fetch('/cart/eliminar', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                            body: JSON.stringify({ item_id: parseInt(itemId) })
                        })
                        .then(function (r) { return r.json(); })
                        .then(function (res) {
                            if (res.success) {
                                const row = document.getElementById('miniRow-' + itemId);
                                if (row) row.remove();
                                document.getElementById('miniCartTotal').textContent = '$' + parseFloat(res.total).toFixed(2);
                                updateCartBadge(res.cart_count);
                                if (res.cart_count === 0) {
                                    itemsEl.classList.add('d-none');
                                    footer.classList.add('d-none');
                                    empty.classList.remove('d-none');
                                }
                            }
                        });
                    });
                });
            })
            .catch(function () {
                loading.classList.add('d-none');
                empty.classList.remove('d-none');
            });
    }

    // Recargar mini-cart después de agregar producto
    const _origAddToCart = window.addToCart;
    window.addToCart = function (productId, quantity) {
        _origAddToCart(productId, quantity);
        if (miniCartEl && miniCartEl.classList.contains('show')) {
            setTimeout(loadMiniCart, 400);
        }
    };
});
