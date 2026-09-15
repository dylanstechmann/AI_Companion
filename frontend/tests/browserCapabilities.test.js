import test from 'node:test';
import assert from 'node:assert/strict';
import { getInstallHelp, getBrowserCapabilities } from '../src/lib/browserCapabilities.js';
import { getPreference, setPreference } from '../src/lib/preferences.js';

test('Firefox installation guidance distinguishes Windows from Linux', () => {
  assert.match(getInstallHelp('Windows NT 10.0 Firefox/143.0'), /143/);
  assert.match(getInstallHelp('X11 Linux Firefox/143.0'), /normal tab/);
  assert.match(getInstallHelp('Android Firefox/143.0'), /browser menu/);
});
test('capability detection works with absent browser APIs', () => {
  assert.deepEqual(getBrowserCapabilities({}, {}), {
    secure: false, microphone: false, speech: false, offlineShell: false, installed: false,
  });
});
test('session preferences do not depend on browser storage', () => {
  assert.equal(getPreference('not-set'), null);
  setPreference('test', true);
  assert.equal(getPreference('test'), 'true');
});
