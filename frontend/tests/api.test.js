import { afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.location = { origin: 'http://localhost:3000' };
Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => storage.delete(key),
} });
const { apiFetch, getSession, setSession, subscribeSession } = await import('../src/api.js');
const originalFetch = globalThis.fetch;
const initial = () => ({ access_token: 'old-access', refresh_token: 'refresh', user: { id: 1 } });
const fresh = () => ({ access_token: 'new-access', refresh_token: 'next-refresh', user: { id: 1 } });
const json = (value, status = 200) => new Response(JSON.stringify(value), { status });
beforeEach(() => setSession(initial()));
afterEach(() => { setSession(null); globalThis.fetch = originalFetch; });

test('attaches Bearer auth while preserving JSON headers, signal and the streaming response', async () => {
  const controller = new AbortController();
  const streamed = new Response('data: hello\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/chat');
    assert.equal(options.headers.get('Authorization'), 'Bearer old-access');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    assert.equal(options.body, '{"message":"hello"}');
    assert.equal(options.signal, controller.signal);
    assert.equal(options.cache, 'no-store');
    return streamed;
  };
  const result = await apiFetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: '{"message":"hello"}', signal: controller.signal });
  assert.equal(result, streamed);
  assert.equal(result.bodyUsed, false);
});

test('preserves multipart bodies without imposing a JSON content type', async () => {
  const body = new FormData();
  body.append('file', new Blob(['audio']), 'voice.wav');
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.body, body);
    assert.equal(options.headers.has('Content-Type'), false);
    assert.equal(options.headers.get('Authorization'), 'Bearer old-access');
    return json({ text: 'hello' });
  };
  assert.equal((await apiFetch('/api/stt', { method: 'POST', body })).status, 200);
});

test('never attaches stored credentials to external, asset or login URLs', async () => {
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.has('Authorization'), false);
    return json({});
  };
  for (const url of ['https://external.test/api/data', '//external.test/api/data',
    '/audio.wav', '/api/auth/login', '/api/auth/demo', '/api/auth/refresh', '/api/auth/options']) {
    await apiFetch(url);
  }
});

test('coalesces concurrent expired-token requests into one refresh and retries once', async () => {
  let refreshes = 0;
  let attempts = 0;
  globalThis.fetch = async (url, options) => {
    if (url === '/api/auth/refresh') {
      refreshes++;
      assert.equal(JSON.parse(options.body).refresh_token, 'refresh');
      return json(fresh());
    }
    attempts++;
    return options.headers.get('Authorization') === 'Bearer new-access' ? json({ ok: true }) : json({}, 401);
  };
  const results = await Promise.all([apiFetch('/api/skills'), apiFetch('/api/config')]);
  assert.ok(results.every((response) => response.ok));
  assert.equal(refreshes, 1);
  assert.equal(attempts, 4);
  assert.equal(getSession().access_token, 'new-access');
});

test('invalid refresh clears the session, storage and notifies the UI', async () => {
  const states = [];
  const unsubscribe = subscribeSession((value) => states.push(value));
  globalThis.fetch = async () => json({}, 401);
  try {
    assert.equal((await apiFetch('/api/skills')).status, 401);
    assert.equal(getSession(), null);
    assert.equal(storage.size, 0);
    assert.deepEqual(states, [null]);
  } finally { unsubscribe(); }
});

test('a second 401 is returned without a refresh loop', async () => {
  let requests = 0;
  globalThis.fetch = async (url) => {
    requests++;
    return url === '/api/auth/refresh' ? json(fresh()) : json({}, 401);
  };
  assert.equal((await apiFetch('/api/skills')).status, 401);
  assert.equal(requests, 3);
  assert.equal(getSession(), null);
});

test('logout during refresh cannot restore credentials or replay the request', async () => {
  let finishRefresh;
  let startedRefresh;
  const started = new Promise((resolve) => { startedRefresh = resolve; });
  let requests = 0;
  globalThis.fetch = async (url) => {
    requests++;
    if (url !== '/api/auth/refresh') return json({}, 401);
    startedRefresh();
    return new Promise((resolve) => { finishRefresh = () => resolve(json(fresh())); });
  };
  const result = apiFetch('/api/skills');
  await started;
  setSession(null);
  finishRefresh();
  assert.equal((await result).status, 401);
  assert.equal(getSession(), null);
  assert.equal(requests, 2);
});

test('an in-flight request cannot be retried for a newly signed-in user', async () => {
  let complete;
  globalThis.fetch = async () => new Promise((resolve) => { complete = resolve; });
  const result = apiFetch('/api/skills');
  setSession({ ...fresh(), user: { id: 2 } });
  complete(json({}, 401));
  assert.equal((await result).status, 401);
  assert.equal(getSession().user.id, 2);
});

test('a valid session survives module reload within the same browser tab', async () => {
  const reloaded = await import('../src/api.js?reload-test');
  assert.deepEqual(reloaded.getSession(), initial());
});

test('an explicitly supplied Authorization header is preserved without refresh interception', async () => {
  let requests = 0;
  globalThis.fetch = async (_url, options) => {
    requests++;
    assert.equal(options.headers.get('Authorization'), 'Bearer explicit');
    return json({}, 401);
  };
  await apiFetch('/api/auth/me', { headers: { Authorization: 'Bearer explicit' } });
  assert.equal(requests, 1);
  assert.equal(getSession().access_token, 'old-access');
});
