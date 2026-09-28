import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

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

test('vite.config.js wires navigateFallback to offline.html and ignores /api/', () => {
  const viteConfigPath = join(root, 'vite.config.js');
  const content = readFileSync(viteConfigPath, 'utf8');
  assert.ok(content.includes("navigateFallback: '/offline.html'"), 'Must specify offline.html navigateFallback');
  assert.ok(content.includes('navigateFallbackDenylist'), 'Must deny api routes from fallback');
});
