/** Invalidate async continuations without retaining their media payloads. */
export function createMediaGeneration() {
  let value = 0;
  return {
    next: () => ++value,
    isCurrent: (token) => token === value,
  };
}

export function selectSpeechVoice(voices, options = {}) {
  const localOnly = options.localOnly !== false;
  const allowed = voices.filter((voice) => !localOnly || voice.localService === true);
  // An explicitly selected remote/missing voice must not fall back to the
  // browser default (which can send text off-device).
  if (options.voiceURI) {
    const selected = allowed.find((voice) => voice.voiceURI === options.voiceURI);
    if (!selected) throw new Error(localOnly
      ? 'The selected voice is not available on this device. Choose a local voice in Settings.'
      : 'The selected browser voice is unavailable. Choose another voice in Settings.');
    return selected;
  }
  if (!allowed.length) throw new Error(localOnly
    ? 'No on-device speech voice is available. Install a local system voice or explicitly allow remote voices in Settings.'
    : 'No browser speech voice is available yet. Try again after voices load or install a system voice.');
  const lang = String(options.lang || '').toLowerCase();
  const matching = lang ? allowed.filter((voice) => voice.lang?.toLowerCase().startsWith(lang)) : allowed;
  return matching.find((voice) => voice.default) || matching[0] ||
    allowed.find((voice) => voice.default) || allowed[0];
}

export function cleanSpeechText(text) {
  return String(text ?? '')
    .replace(/```[\s\S]*?```/g, ' code block ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/!\[.*?\]\(.*?\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[#*_~>]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Supports callback-only WebKit and promise-based decodeAudioData. */
export function decodeMediaAudio(context, bytes) {
  return new Promise((resolve, reject) => {
    try {
      const result = context.decodeAudioData(bytes, resolve, reject);
      if (result?.then) result.then(resolve, reject);
    } catch (error) { reject(error); }
  });
}

export function setMediaPlaybackState(session, state) {
  try { if (session) session.playbackState = state; } catch { /* Partial implementation. */ }
}

export function registerMediaActions(session, handlers) {
  if (typeof session?.setActionHandler !== 'function') return () => {};
  const registered = [];
  for (const [action, handler] of Object.entries(handlers)) {
    try { session.setActionHandler(action, handler); registered.push(action); } catch { /* Unsupported action. */ }
  }
  return () => {
    for (const action of registered) {
      try { session.setActionHandler(action, null); } catch { /* Session unavailable. */ }
    }
  };
}
