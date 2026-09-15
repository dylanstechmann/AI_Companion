import { test, expect } from '@playwright/test';

test('studio makes no API/CDN requests and controls remain usable', async ({ page }) => {
  const outbound = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api') || (url.protocol.startsWith('http') && url.hostname !== '127.0.0.1')) outbound.push(request.url());
  });
  await page.goto('/#avatar-studio');
  await expect(page.getByRole('heading', { name: 'AI Companion', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Tiffany Thoughtful & analytical' }).click();
  await expect(page.locator('.studio-stage-caption h2')).toHaveText('Tiffany');
  await page.getByRole('button', { name: 'happy', exact: true }).click();
  await expect(page.getByRole('button', { name: 'happy', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Test mouth motion', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop mouth motion', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Stop mouth motion', exact: true }).click();
  await page.getByRole('button', { name: 'Pause animation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test mouth motion', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Resume animation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test mouth motion', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Browser & privacy' }).click();
  await expect(page.getByText('Fonts and bundled 3D assets', { exact: false })).toBeVisible();
  expect(outbound).toEqual([]);
});

test('camera, quality, pause and reduced-motion controls', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Firefox headless sandbox has no WebGL; fallback tested separately.');
  await page.goto('/#avatar-studio');
  await expect(page.locator('.avatar3d-status')).toHaveText('Live motion', { timeout: 45000 });
  await page.getByRole('button', { name: 'Body', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Body', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByLabel('Avatar rendering quality').selectOption('eco');
  await expect(page.getByLabel('Avatar rendering quality')).toHaveValue('eco');
  await page.getByLabel('Avatar rendering quality').selectOption('high');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.getByRole('button', { name: 'Portrait', exact: true }).click();
  await page.getByRole('button', { name: 'Pause animation', exact: true }).click();
  await expect(page.locator('.avatar3d-stage')).toHaveAttribute('data-motion', 'still');
  await expect(page.locator('.avatar3d-status')).toContainText('Motion paused');
  await page.getByRole('button', { name: 'Resume animation', exact: true }).click();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.avatar3d-stage')).toHaveAttribute('data-motion', 'still');
  await expect(page.locator('.avatar3d-status')).toContainText('Reduced motion');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(page.locator('.avatar3d-stage')).toHaveAttribute('data-motion', 'active');
});

test('mobile preview has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/#avatar-studio');
  await page.getByRole('button', { name: 'Procedural companion Lightweight fallback' }).click();
  await expect(page.locator('.studio-stage-caption h2')).toHaveText('Procedural companion');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('.studio').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.getByRole('button', { name: 'Browser & privacy' }).click();
  await expect(page.locator('.studio-privacy')).toBeVisible();
});

test('missing GLB recovers to a procedural avatar, then retry reloads', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Requires WebGL in this sandbox.');
  await page.route('**/avatars/greg_3d.glb', route => route.fulfill({ status: 404, body: 'Missing test model' }));
  await page.goto('/#avatar-studio');
  await expect(page.locator('.avatar3d-status')).toContainText('model unavailable', { timeout: 45000 });
  await page.unroute('**/avatars/greg_3d.glb');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('.avatar3d-status')).toHaveText('Live motion', { timeout: 45000 });
});

test('WebGL failure preserves the studio UI and exposes retry', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      if (String(type).includes('webgl')) return null;
      return original.call(this, type, ...args);
    };
  });
  await page.goto('/#avatar-studio');
  await expect(page.getByText('3D view unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry 3D view' })).toBeVisible();
  await page.getByRole('button', { name: 'Browser & privacy' }).click();
  await expect(page.locator('.studio-privacy')).toBeVisible();
});

test('chat and privacy settings work with storage disabled and a mocked backend', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage unavailable'); } });
    Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('Storage unavailable'); } });
  });
  const requests = [];
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    let data = {};
    if (path === '/api/auth/demo') data = { user: { id: 'test', username: 'Test user', credits: 10 }, access_token: 'not-a-real-token' };
    else if (path === '/api/characters') data = [{ id: 'greg', name: 'Greg', description: 'Test fixture', avatar_3d_url: '/avatars/greg_3d.glb' }];
    else if (path.endsWith('/messages')) data = [];
    else if (path === '/api/health') data = { status: 'healthy', gpu_available: false };
    else if (path === '/api/config') data = { stt_mode: 'local' };
    else if (path === '/api/chat') {
      await route.fulfill({ contentType: 'text/event-stream', body: 'data: {"text":"Test reply from mocked backend."}\n\ndata: [DONE]\n\n' });
      return;
    }
    await route.fulfill({ json: data });
  });
  await page.goto('/');
  await expect(page.getByText('Chat with Greg', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Hide avatar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Show avatar', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Show avatar', exact: true }).click();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(page.getByText('Only use voices the browser reports as local', { exact: false })).toBeVisible();
  await expect(page.getByRole('checkbox')).toBeChecked();
  await page.getByRole('button', { name: 'TTS is on', exact: true }).click();
  await page.getByRole('button', { name: 'Close settings', exact: true }).click();
  await page.locator('textarea').fill('Hello from a local test');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByText('Test reply from mocked backend.', { exact: true })).toBeVisible();
  expect(requests).not.toContain('/api/stt');
  expect(requests).not.toContain('/api/tts');
});
