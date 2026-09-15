// Probe without constructing a renderer, so unavailable WebGL2 becomes an
// ordinary UI state instead of an exception from React Three Fiber.
export function probeAvatarWebGL(createCanvas) {
  let context;
  try {
    context = createCanvas().getContext('webgl2', {
      alpha: true, antialias: true, failIfMajorPerformanceCaveat: false,
    });
    return Boolean(context);
  } catch {
    return false;
  } finally {
    // A temporary probe must not consume a persistent GPU context.
    try { context?.getExtension('WEBGL_lose_context')?.loseContext(); } catch { /* driver already lost */ }
  }
}

let cachedSupport;
export function avatarWebGLAvailable(force = false) {
  if (typeof document === 'undefined') return false;
  if (force || cachedSupport === undefined) {
    cachedSupport = probeAvatarWebGL(() => document.createElement('canvas'));
  }
  return cachedSupport;
}
