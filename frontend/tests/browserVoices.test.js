import assert from 'node:assert/strict';
import { test } from 'node:test';
import { subscribeBrowserVoices } from '../src/browserVoices.js';

test('settings and playback receive delayed voices and can unsubscribe independently', () => {
  const synthesis = new EventTarget();
  let voices = [];
  synthesis.getVoices = () => voices;
  const settings = [];
  const playback = [];
  const closeSettings = subscribeBrowserVoices(synthesis, (list) => settings.push(list));
  const stopPlayback = subscribeBrowserVoices(synthesis, (list) => playback.push(list));
  voices = ['voice one'];
  synthesis.dispatchEvent(new Event('voiceschanged'));
  closeSettings();
  voices = ['voice two'];
  synthesis.dispatchEvent(new Event('voiceschanged'));
  stopPlayback();
  assert.deepEqual(settings, [[], ['voice one']]);
  assert.deepEqual(playback, [[], ['voice one'], ['voice two']]);
});
