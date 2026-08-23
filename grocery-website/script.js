// Client-Side Cart, DB Synchronizer & Order Placer

const DEFAULT_CUSTOMER_NAMES = [
    "Priya Patel", "Rahul Verma", "Sneha Iyer", "Aarav Sharma", 
    "Meera Kumar", "Vikram Reddy", "Swati Gupta", "Karthik Bhat"
];

// 1. Live Date & Time Clock
function updateDateTime() {
    const dtEl = document.getElementById('live-datetime');
    if (!dtEl) return;

    const now = new Date();
    const options = {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
    };
    dtEl.innerText = now.toLocaleString('en-IN', options);
}
updateDateTime();
setInterval(updateDateTime, 1000);

// 2. Toast Notification
function showToast(message) {
    const toast = document.getElementById('cart-toast');
    toast.innerText = message;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 2500);
}

// 3. Initial Load: Fetch existing active cart from store.db
async function syncCartBadge() {
    try {
        const resp = await fetch('/api/cart');
        const res = await resp.json();
        if (res.success) {
            document.getElementById('cart-count').innerText = res.total_items;
        }
    } catch (e) {
        console.log('Cart sync error:', e);
    }
}
syncCartBadge();

// 4. Add to Cart: Immediately Inserts/Updates the `cart` Table in `store.db`
async function addToCart(itemName, price) {
    try {
        const resp = await fetch('/api/cart/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_name: itemName, price: price })
        });
        const res = await resp.json();

        if (res.success) {
            document.getElementById('cart-count').innerText = res.total_cart_items;
            showToast(`🛒 Saved to store.db: "${itemName}" (Qty: ${res.item_qty})`);
        } else {
            showToast('Error adding to cart: ' + res.error);
        }
    } catch (e) {
        showToast('Server error: ' + e.message);
    }
}

// 5. Open Cart Modal & Render Items Fetched Directly from `store.db`
async function openCartModal() {
    const modal = document.getElementById('cart-modal');
    const tbody = document.getElementById('cart-items-tbody');
    const buyBtn = document.getElementById('btn-cart-buy');

    tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 2rem;">⏳ Fetching active cart from store.db...</td></tr>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch('/api/cart');
        const res = await resp.json();

        if (!res.success || res.items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" class="empty-cart-msg">
                        🛍️ Your shopping cart is empty in database.<br>Click <b>"+ Add to Cart"</b> on any item to add it here!
                    </td>
                </tr>
            `;
            document.getElementById('bill-subtotal').innerText = '₹0.00';
            document.getElementById('bill-tax').innerText = '₹0.00';
            document.getElementById('bill-delivery').innerText = '₹0.00';
            document.getElementById('bill-grand-total').innerText = '₹0.00';
            buyBtn.disabled = true;
            return;
        }

        buyBtn.disabled = false;
        tbody.innerHTML = '';

        let subtotal = res.subtotal;

        res.items.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="item-name-cell">${item.product_name}</td>
                <td><span class="item-freq-pill">Qty: ${item.quantity}</span></td>
                <td class="item-price-cell">₹${item.total_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
            `;
            tbody.appendChild(tr);
        });

        // Bill Breakdown Math
        const gstTax = Math.round(subtotal * 0.05 * 100) / 100; // 5% GST on grocery
        const deliveryFee = subtotal >= 499 ? 0.00 : 40.00;
        const grandTotal = Math.round((subtotal + gstTax + deliveryFee) * 100) / 100;

        document.getElementById('bill-subtotal').innerText = `₹${subtotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        document.getElementById('bill-tax').innerText = `₹${gstTax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        document.getElementById('bill-delivery').innerText = deliveryFee === 0.00 ? 'FREE' : `₹${deliveryFee.toFixed(2)}`;
        document.getElementById('bill-grand-total').innerText = `₹${grandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

        // Attach grandTotal for placement
        modal.dataset.grandTotal = grandTotal;

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="3" style="color: red; text-align: center;">Error loading cart: ${e.message}</td></tr>`;
    }
}

// 6. Close Cart Modal
function closeCartModal() {
    document.getElementById('cart-modal').style.display = 'none';
}

// 7. Place Order Button Handler (Converts active cart into PENDING order in store.db)
async function handlePlaceOrder() {
    const buyBtn = document.getElementById('btn-cart-buy');
    const modal = document.getElementById('cart-modal');
    const grandTotal = parseFloat(modal.dataset.grandTotal || 0.0);

    if (grandTotal <= 0) return;

    buyBtn.disabled = true;
    buyBtn.innerText = '⏳ Finalizing Order in store.db...';

    const randomCustomer = window.CURRENT_SIM_CUSTOMER || DEFAULT_CUSTOMER_NAMES[Math.floor(Math.random() * DEFAULT_CUSTOMER_NAMES.length)];

    try {
        const resp = await fetch('/api/create-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                customer_name: randomCustomer,
                order_date: window.CURRENT_SIM_DATE || null,
                gross_amount: grandTotal
            })
        });
        const res = await resp.json();

        if (res.success) {
            alert(`✅ Order Created Successfully in store.db!\n\nOrder ID: ${res.order_id}\nCustomer: ${res.customer_name}\nGrand Total: ₹${res.gross_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}\nStatus: PENDING ⏳\n\n(Linked cart items to ${res.order_id} in 'cart' table)`);

            document.getElementById('cart-count').innerText = '0';
            closeCartModal();
            showToast(`🎉 ${res.order_id} saved to orders table! (PENDING)`);
        } else {
            alert('Error creating order: ' + res.error);
        }
    } catch (e) {
        alert('Network Error: ' + e.message);
    } finally {
        buyBtn.disabled = false;
        buyBtn.innerText = '🛍️ Place Order / Buy Now';
    }
}

// Close modal on background click
window.addEventListener('click', (e) => {
    const modal = document.getElementById('cart-modal');
    if (e.target === modal) {
        closeCartModal();
    }
});
