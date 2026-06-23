/**
 * Admin auth store — lightweight API key auth.
 *
 * In dev (no ADMIN_API_KEY set on the backend) everything passes.
 * In prod the key is stored in sessionStorage and sent as X-Admin-Key.
 */

let _key = $state(typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('admin_key') || '' : '');
let _authed = $state(false);
let _checking = $state(true);

function _authHeaders() {
  return _key ? { 'X-Admin-Key': _key } : {};
}

// Verify on load
if (typeof fetch !== 'undefined') {
  (async () => {
    try {
      const res = await fetch('/api/admin/check', { headers: _authHeaders() });
      const data = await res.json();
      _authed = data.ok === true;
    } catch {
      _authed = false;
    }
    _checking = false;
  })();
}

export const auth = {
  get key() { return _key; },
  get authed() { return _authed; },
  get checking() { return _checking; },

  async prompt() {
    const input = window.prompt('Admin API key:');
    if (!input) return;
    _key = input;
    sessionStorage.setItem('admin_key', input);
    try {
      const res = await fetch('/api/admin/check', { headers: { 'X-Admin-Key': input } });
      if (res.ok) {
        _authed = true;
      } else {
        _authed = false;
        sessionStorage.removeItem('admin_key');
        _key = '';
        alert('Invalid admin key');
      }
    } catch {
      _authed = false;
    }
  },

  logout() {
    _key = '';
    _authed = false;
    sessionStorage.removeItem('admin_key');
  },
};

/** Fetch wrapper that attaches the admin key header. */
export async function authFetch(url, options = {}) {
  const headers = { ...options.headers };
  if (_key) headers['X-Admin-Key'] = _key;
  return fetch(url, { ...options, headers });
}
