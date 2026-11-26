import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';

const root = process.cwd();

test('offline.html exists and provides a responsive offline fallback experience', () => {
  const offlinePath = join(root, 'public/offline.html');
  assert.ok(existsSync(offlinePath), 'public/offline.html must exist');
  const content = readFileSync(offlinePath, 'utf8');
  assert.ok(content.includes('Connection Paused') || content.includes('Offline'), 'Must have offline header');
  assert.ok(content.includes('checkConnection'), 'Must have reconnect check function');
  assert.ok(content.includes('net-status'), 'Must have network status diagnostic indicator');
});

test('public/manifest.json contains enhanced PWA install metadata and shortcuts', () => {
  const manifestPath = join(root, 'public/manifest.json');
  assert.ok(existsSync(manifestPath), 'public/manifest.json must exist');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));

  assert.equal(manifest.name, 'AI Companion');
  assert.equal(manifest.short_name, 'AI Companion');
  assert.equal(manifest.display, 'standalone');
  assert.ok(manifest.id, 'PWA must declare an app id');
  assert.ok(Array.isArray(manifest.categories) && manifest.categories.includes('productivity'), 'Must have categories');
  assert.ok(Array.isArray(manifest.shortcuts) && manifest.shortcuts.length >= 2, 'Must provide shortcuts for Voice and Avatars');

  const voiceShortcut = manifest.shortcuts.find((s) => s.short_name === 'Voice');
  assert.ok(voiceShortcut, 'Must have Voice shortcut');

  const has192 = manifest.icons.some((i) => i.sizes === '192x192' && i.purpose?.includes('maskable'));
  const has512 = manifest.icons.some((i) => i.sizes === '512x512' && i.purpose?.includes('maskable'));
  assert.ok(has192 && has512, 'Must include maskable 192x192 and 512x512 icons');
});

test('vite.config.js uses offline.html only as a fallback for app navigations', () => {
  const viteConfigPath = join(root, 'vite.config.js');
  const content = readFileSync(viteConfigPath, 'utf8');
  const match = content.match(/urlPattern: ([\s\S]*?),\s*handler: 'NetworkOnly'/);
  assert.ok(match, 'Must route app navigation over the network');
  assert.ok(content.includes('navigateFallback: null'));
  assert.ok(content.includes("'**/index.html'"), 'The entry document must use the navigation strategy');
  assert.ok(content.includes("precacheFallback: { fallbackURL: '/offline.html' }"));
  assert.ok(!content.includes('networkTimeoutSeconds'), 'Workbox build rejects this option for NetworkOnly');
  const matches = runInNewContext(match[1]);
  const request = { mode: 'navigate' };
  assert.equal(matches({ request, sameOrigin: true, url: new URL('https://example.test/?mode=voice') }), true);
  assert.equal(matches({ request, sameOrigin: true, url: new URL('https://example.test/api/health') }), false);
  assert.equal(matches({ request, sameOrigin: false, url: new URL('https://example.test/') }), false);
  const successHandler = content.match(/fetchDidSucceed: ([\s\S]*?\n\s*\}),/);
  assert.ok(successHandler);
  const handle = runInNewContext(successHandler[1]);
  for (const status of [200, 404]) {
    const response = { status };
    assert.equal(handle({ response }), response);
  }
  assert.throws(() => handle({ response: { status: 502 } }), /frontend unavailable/);
});

async function checkReconnect(initialURL, destination, expectedNavigation) {
  const markup = readFileSync(join(root, 'public/offline.html'), 'utf8');
  const script = markup.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);

  const initial = new URL(initialURL, 'https://example.test');
  const navigations = [];
  const requested = [];
  const events = {};
  const retryButton = {
    disabled: false,
    addEventListener: (name, handler) => { events[name] = handler; },
  };
  const retryStatus = { textContent: '' };
  const elements = { 'net-status': {}, 'retry-btn': retryButton, 'retry-status': retryStatus };
  const health = { ok: true, json: async () => ({ status: 'ok' }) };
  const responses = [
    { ok: false },
    health,
    { ok: false },
    health,
    { ok: true, headers: new Headers({ 'Content-Type': 'text/html; charset=utf-8' }) },
  ];
  runInNewContext(script, {
    AbortController,
    document: { getElementById: (id) => elements[id] },
    navigator: { onLine: true },
    fetch: async (url) => {
      requested.push(url);
      return responses.shift();
    },
    window: {
      location: {
        pathname: initial.pathname,
        href: initial.href,
        replace: (url) => navigations.push(['replace', url]),
        reload: () => navigations.push(['reload']),
      },
      addEventListener: (name, handler) => { events[name] = handler; },
      setInterval: () => 1,
      clearInterval: () => {},
      setTimeout: () => 2,
      clearTimeout: () => {},
    },
  });

  await events.online();
  assert.deepEqual(navigations, []);
  assert.match(retryStatus.textContent, /server unavailable/);
  await events.click();
  assert.deepEqual(navigations, []);
  await events.click();
  assert.deepEqual(requested, ['/api/health', '/api/health', destination, '/api/health', destination]);
  assert.deepEqual(navigations, [expectedNavigation]);
}

test('reconnect reloads a shortcut document after both probes succeed', async () => {
  for (const url of ['/?mode=voice', '/?mode=voice#saved', '/index.html?tab=characters#selected']) {
    await checkReconnect(url, new URL(url, 'https://example.test').href, ['reload']);
  }
});

test('reconnect navigates a directly opened offline page to the app root', async () => {
  await checkReconnect('/offline.html#preview', '/', ['replace', '/']);
});
