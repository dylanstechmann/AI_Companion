// One session per browser tab. Credentials never go into URLs or cross-origin requests.
const STORAGE_KEY = 'ai-companion-session';
const listeners = new Set();
let session = loadSession();
let refreshPromise = null;

function loadSession() {
  try {
    const saved = JSON.parse(globalThis.sessionStorage?.getItem(STORAGE_KEY) || 'null');
    return saved?.access_token && saved?.user ? saved : null;
  } catch {
    return null;
  }
}

export function getSession() { return session; }

export function setSession(value) {
  session = value;
  try {
    if (value) globalThis.sessionStorage?.setItem(STORAGE_KEY, JSON.stringify(value));
    else globalThis.sessionStorage?.removeItem(STORAGE_KEY);
  } catch { /* Storage may be disabled; keep an in-memory session. */ }
  listeners.forEach((listener) => listener(session));
}

export function subscribeSession(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

async function refreshSession(previous) {
  if (!refreshPromise) {
    const pending = (async () => {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: previous.refresh_token }),
        cache: 'no-store',
      });
      // Never restore a session after logout or overwrite a newer login.
      if (session !== previous) return;
      if (!response.ok) {
        setSession(null);
        return;
      }
      const next = await response.json();
      if (session === previous) setSession(next?.access_token && next?.user ? next : null);
    })();
    refreshPromise = pending;
    try { await pending; }
    finally { if (refreshPromise === pending) refreshPromise = null; }
  } else {
    await refreshPromise;
  }
}

export async function apiFetch(input, options = {}) {
  const url = new URL(input, globalThis.location.origin);
  const isApi = url.origin === globalThis.location.origin && url.pathname.startsWith('/api/');
  const isPublicAuth = /^\/api\/auth\/(login|register|refresh|demo|options)\/?$/.test(url.pathname);
  const headers = new Headers(options.headers);
  const previous = session;
  const attachToken = isApi && !isPublicAuth && previous?.access_token && !headers.has('Authorization');
  if (attachToken) headers.set('Authorization', `Bearer ${previous.access_token}`);
  const request = { ...options, headers, ...(isApi ? { cache: 'no-store' } : {}) };
  let response = await fetch(input, request);
  if (response.status !== 401 || !attachToken) return response;

  if (session === previous) {
    if (previous.refresh_token) await refreshSession(previous);
    else setSession(null);
  }
  // A request started under an older login must never be replayed for a new user.
  if (!session || session.user.id !== previous.user.id) return response;
  const retriedSession = session;
  headers.set('Authorization', `Bearer ${retriedSession.access_token}`);
  response = await fetch(input, { ...request, headers });
  if (response.status === 401 && session === retriedSession) setSession(null);
  return response;
}
