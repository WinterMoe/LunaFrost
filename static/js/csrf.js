function getCSRFToken() {
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        return tokenMeta.getAttribute('content');
    }

    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            return decodeURIComponent(value);
        }
    }

    return null;
}

window.fetchWithCSRF = function (url, options = {}) {
    const token = getCSRFToken();
    
    if (token) {
        // For FormData, add token to FormData itself, not headers
        if (options.body instanceof FormData) {
            options.body.append('csrf_token', token);
            // Don't set Content-Type header for FormData - browser will set it with boundary
            // Don't modify options.headers for FormData to avoid breaking multipart boundary
        } else {
            // For JSON and other content types, add token to headers
            options.headers = options.headers || {};
            options.headers['X-CSRFToken'] = token;
        }
    }

    return fetch(url, options);
};

window.getCSRFToken = getCSRFToken;
