// Interactive Cart & Shopping Logic
let cartCount = 0;

function showToast(message) {
    const toast = document.getElementById('cart-toast');
    toast.innerText = message;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 2500);
}

function addToCart(itemName, price) {
    cartCount++;
    document.getElementById('cart-count').innerText = cartCount;
    showToast(`🛒 Added 1x "${itemName}" (₹${price}) to cart!`);
}

function buyNow(itemName, price) {
    cartCount++;
    document.getElementById('cart-count').innerText = cartCount;
    showToast(`🛍️ Order placed for "${itemName}" (₹${price})!`);
}

function openCart() {
    if (cartCount === 0) {
        showToast("🛍️ Your cart is empty. Add items to checkout!");
    } else {
        showToast(`🛍️ Your cart has ${cartCount} item(s) ready.`);
    }
}
