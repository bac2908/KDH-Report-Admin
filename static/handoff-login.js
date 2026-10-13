'use strict';
const form = document.getElementById('handoff-login');
form.addEventListener('submit', async event => {
    event.preventDefault();
    const error = document.getElementById('handoff-error');
    try {
        const response = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-KDH-Request': '1'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))});
        if (!response.ok) throw new Error((await response.json()).error || 'Chưa đăng nhập được.');
        location.replace('/viewer/authorize?transaction=' + encodeURIComponent(form.dataset.transaction));
    } catch (failure) { error.textContent = failure.message; }
});
