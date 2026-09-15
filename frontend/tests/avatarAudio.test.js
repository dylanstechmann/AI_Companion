import test from 'node:test';
import assert from 'node:assert/strict';
import { createAvatarAudioDriver } from '../src/lib/avatarAudio.js';

function harness() {
  const callbacks = new Map();
  const amplitudeRef = { current: 0 };
  let time = 0;
  let id = 0;
  const driver = createAvatarAudioDriver({
    amplitudeRef,
    now: () => time,
    schedule: (fn) => { callbacks.set(++id, fn); return id; },
    cancel: (key) => callbacks.delete(key),
  });
  const step = (milliseconds = 1000 / 30) => {
    time += milliseconds;
    const scheduled = [...callbacks.values()];
    callbacks.clear();
    scheduled.forEach((fn) => fn());
  };
  return { driver, callbacks, amplitudeRef, step };
}

test('stopped audio does not create an idle closing loop', () => {
  const { driver, callbacks } = harness();
  driver.stopTracking();
  driver.stopTracking();
  assert.equal(callbacks.size, 0);
});

test('switching simulation/analyser never leaves competing timers', () => {
  const { driver, callbacks, amplitudeRef, step } = harness();
  driver.startSimulation();
  driver.startSimulation();
  assert.equal(callbacks.size, 1);
  step();
  assert.ok(amplitudeRef.current > 0);
  driver.trackAnalyser({ fftSize: 32, getByteTimeDomainData: (data) => data.fill(128) });
  assert.equal(callbacks.size, 1);
  for (let i = 0; i < 30; i++) step();
  assert.ok(amplitudeRef.current < 0.001);
  driver.startSimulation();
  assert.equal(callbacks.size, 1);
  step();
  assert.ok(amplitudeRef.current > 0.01);
  driver.stopTracking();
  for (let i = 0; i < 30; i++) step();
  assert.equal(amplitudeRef.current, 0);
  assert.equal(callbacks.size, 0);
});

test('pause/offscreen and document visibility suspend analysis without stopping audio mode', () => {
  const { driver, callbacks, amplitudeRef, step } = harness();
  let reads = 0;
  driver.trackAnalyser({ fftSize: 32, getByteTimeDomainData(data) { reads++; data.fill(128); } });
  step();
  assert.equal(reads, 1);
  driver.setVisualActive(false);
  assert.equal(callbacks.size, 0);
  step();
  assert.equal(reads, 1);
  assert.equal(amplitudeRef.current, 0);
  driver.setDocumentVisible(false);
  driver.setVisualActive(true);
  assert.equal(callbacks.size, 0);
  driver.setDocumentVisible(true);
  assert.equal(callbacks.size, 1);
  step(60000);
  assert.equal(reads, 2);
  assert.ok(amplitudeRef.current >= 0 && amplitudeRef.current <= 1);
});

test('cleanup cancels timers and never disconnects externally owned audio nodes', () => {
  const { driver, callbacks, amplitudeRef, step } = harness();
  let disconnected = false;
  driver.trackAnalyser({
    fftSize: 32, getByteTimeDomainData: (data) => data.fill(128),
    disconnect() { disconnected = true; },
  });
  driver.dispose();
  step();
  assert.equal(callbacks.size, 0);
  assert.equal(amplitudeRef.current, 0);
  assert.equal(disconnected, false);
  // React Strict Mode can re-run the hook's effects after a cleanup.
  driver.startSimulation();
  step();
  assert.ok(amplitudeRef.current > 0);
});

test('detached analyser errors close the mouth gracefully and terminate', () => {
  const { driver, callbacks, amplitudeRef, step } = harness();
  amplitudeRef.current = 0.8;
  driver.trackAnalyser({ fftSize: 32, getByteTimeDomainData() { throw new Error('detached'); } });
  for (let i = 0; i < 30; i++) step();
  assert.equal(amplitudeRef.current, 0);
  assert.equal(callbacks.size, 0);
});
