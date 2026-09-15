# AI Companion: 3D, Firefox, and Privacy Update

Prepared September 15, 2026 for the AI_Companion project. This update improves the existing app rather than replacing it, and includes a backend-disconnected avatar studio for safe visual review.

## What changed

- **3D correctness:** Skeleton-safe cloning, preserved body morphs, corrected eye placement on Greg, Tiffany, and Friendly AI, and scoped eye shading with white sclera, smaller colored irises, and pupils. Source GLBs remain unchanged.
- **Presentation:** Improved portrait framing, full-body view, camera reset, three-point lighting, material repairs for the known bundled assets, and Eco/Balanced/High controls.
- **Motion and performance:** Independent head, neck, and gaze movement; damped facial expressions; amplitude-driven mouth movement; stable model caching; one-time contact shadows. Autonomous rendering stops when paused, hidden, offscreen, or reduced motion is requested.
- **Resilience:** Missing-model procedural fallback, WebGL-unavailable static fallback, retry controls, and explicit resource ownership/cleanup.
- **Voice:** Actual supported recording MIME types instead of assuming WebM, bounded silent recordings, serial transcription, cancellation-safe capture/playback, and automatic microphone muting when the tab becomes hidden. No silent audio keepalive. Browser speech defaults to voices reported as local, with no silent switch to another provider on failure.
- **Chat integration:** Speech errors are visible; pending cloud speech requests can be stopped and are invalidated on conversation changes. Recorder capture is suppressed while assistant speech is pending or playing.
- **Privacy/PWA:** Self-hosted font files, valid install icons, a single generated manifest, browser capability/install guidance, and no runtime caching of API responses. Preferences are page-session-only and reset on reload; conversation data is still held by the existing backend.
- **Backend Firefox:** Optional `BROWSER_ENGINE=firefox`; Chromium remains the default. Engine-specific arguments, restricted browser contexts, sanitized error logs, and conservative URL/DNS checks were added. Docker installs both engines; changing ENTRYPOINT to CMD fixes the production command override.
- **Maintenance:** Updated dependency lockfile, unit/browser tests, and a GitHub Actions workflow. CI has been authored but has not run on GitHub until the branch is pushed.

## Firefox and the privacy question

Frontend browser compatibility and backend browser automation are separate. You can open the companion in Firefox without configuring the backend to use Firefox, and vice versa.

Mozilla documents Windows web-app support in Firefox 143 onward, with Microsoft Store builds requiring Firefox 150 or later; that feature is not currently offered on macOS/Linux ([Mozilla guidance](https://support.mozilla.org/en-US/kb/web-apps-firefox-windows)). Browser and platform install capabilities vary, so the UI provides guidance rather than pretending every platform exposes an identical PWA installation flow ([MDN installability guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)).

There was no evidence in the inspected code that prior Chrome or Safari choices were made for surveillance or control. This is a code review, not a way to establish another tool's intent. The actionable privacy issues are the actual data destinations, recording lifecycle, storage policy, authentication boundaries, and permissions.

The recorder uses feature detection because supported recording formats vary, and a positive support check does not guarantee resources will always be available ([MDN MediaRecorder guidance](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static)).

## Validation completed

| Check | Result | Scope |
|---|---|---|
| Frontend unit tests | 50 passed | Actual bundled GLB invariants, cloning, eye repair/shader setup, facial math, rendering availability, audio lifecycle, MIME handling, preferences |
| Backend tests | 39 passed | Mocked Playwright/DNS behavior, lifecycle cleanup, settings validation and fresh-process import |
| Browser integration | 10 passed; 2 intentionally skipped | Chromium and Firefox UI, mocked chat, storage unavailable, mobile overflow, privacy controls; Chromium also exercised renderer controls and missing-model recovery |
| Production frontend build | Passed | Vite build and PWA generation; large lazy 3D chunk warning remains |
| Dependency audit | 0 reported npm vulnerabilities | Point-in-time audit, not proof of complete security |
| Source checks | Passed | Python syntax, Compose YAML parsing, git whitespace/diff checks |
| Visual inspection | Completed | All three repaired avatars in Chromium software WebGL; desktop and mobile layout |

The two skipped browser cases require WebGL that this environment cannot provide to headless Firefox. Firefox UI and no-WebGL fallback passed, but actual Firefox GPU rendering is not verified. Live cloud providers, physical microphone capture, Safari/iOS, Docker image startup, and end-to-end backend browser sessions have not been tested. Browser chat tests use mock responses and do not prove real provider connectivity.

The isolated preview never connects the backend, chat history, microphone, or AI services. Normal frontend builds still require the project's backend configuration.

## Important limits

- **Not production secure:** Unauthenticated powerful endpoints, a shared demo-user fallback, incomplete ownership checks, and insufficient execution isolation remain. Do not expose the backend to the public internet or load sensitive credentials into it.
- **Not fully local:** Configured LLM, embedding, cloud speech, and other remote provider flows still send data externally. Firefox does not change those destinations.
- **Not a network sandbox:** DNS and request interception checks cannot reliably contain redirects, rebinding, proxy resolution, or all non-HTTP traffic. Browser service callers also still need successful-session cleanup and persistent-session semantics.
- **Not new character art:** Original A-pose arms, simplified facial geometry, hair, and authored textures remain. Models are roughly 12–22 MB, with some large textures. Quality presets reduce rendering cost, not asset download size.
- **Not phoneme lip sync:** Cloud audio drives mouth opening from amplitude. Browser TTS and the studio mouth test use simulated cadence. There are no new retargeted animation clips or artist-authored visemes.
- **Not offline AI:** The service worker caches the shell, not API data, chat history, audio, or the large model files.

The companion should remain a local development prototype until the blocking security items are resolved. The detailed [browser/privacy audit](browser-privacy-audit.md) explains risks and mitigations with code pointers.

## Recommended next work

- **Security first:** Require authentication by default, remove shared demo fallback outside explicit development mode, enforce per-user resource ownership, isolate execution from secrets and host files, and add explicit approval for consequential tool actions.
- **Browser sessions:** Introduce scoped session IDs and guaranteed teardown, network-level egress restrictions, and authenticated API ownership before expanding automation.
- **Asset pipeline:** Create retargeted idle poses, improve eyelids and facial morphs, compress meshes/textures, and add measured loading/memory budgets.
- **Device QA:** Test real Firefox GPU rendering, Android installation, Safari/iOS recording/playback, permission revocation, and backgrounding on actual hardware.

## Reproducing the work

```bash
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium firefox
npm run test:e2e
npm run build:studio

cd ..
python -m pip install pydantic-settings
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend/tests -v
```

To inspect without providers, run `npm run dev` in `frontend` and open `http://localhost:3000/#avatar-studio`. To use backend Firefox, set `BROWSER_ENGINE=firefox` in `.env` and rebuild the backend container. Never commit real `.env` secrets.
