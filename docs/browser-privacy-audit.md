# Browser privacy and security audit

**Scope:** local static review and offline mocked tests, 15 September 2026.
**Decision:** keep Chromium as the backend default; offer Firefox as an explicit
configuration choice, not as a claim of anonymity or a security boundary.

## What changed

- `BROWSER_ENGINE` is validated as `Literal["chromium", "firefox"]`, defaulting
  to `"chromium"`; the service also rejects invalid values if settings are
  replaced or mutated outside normal validation. [Configuration](../backend/app/config.py),
  [browser startup](../backend/app/browser.py).
- The backend selects Playwright's matching engine; only Chromium receives the
  existing `--no-sandbox` and `--disable-dev-shm-usage` switches. Firefox receives
  neither Chromium switch, and there is no silent engine fallback.
  [Browser startup](../backend/app/browser.py).
- The image installs both Playwright browser packages and their OS dependencies;
  both Compose variants pass through `BROWSER_ENGINE` with a Chromium default
  and retain `.env` loading for `PROXY_URL` and other settings.
  [Dockerfile](../backend/Dockerfile), [development Compose](../docker-compose.yml),
  [production Compose](../docker-compose.production.yml), [environment example](../.env.example).
- The Dockerfile now uses `CMD` instead of a fixed Uvicorn `ENTRYPOINT`, so
  production Compose replaces the development command and omits `--reload`
  rather than appending a second Uvicorn invocation.
  No container user/privilege policy was changed.
  [Dockerfile](../backend/Dockerfile), [production Compose](../docker-compose.production.yml),
  [startup contract test](../backend/tests/test_browser_config.py).
- Each service creates a fresh non-persistent browser context with
  `permissions=[]`, `service_workers="block"` and `accept_downloads=False`;
  it does not import a user's existing browser profile, cookies or logins.
  These restrictions apply to backend automation, not to the frontend PWA.
  [Context creation](../backend/app/browser.py).
- Startup is serialized, partial startup failures/cancellation attempt cleanup,
  and explicit `close()` attempts context, browser and driver cleanup even if
  a preceding close fails or is cancelled; repeated close calls are harmless.
  This does **not** repair callers that never call `close()`.
  [Lifecycle implementation](../backend/app/browser.py),
  [lifecycle tests](../backend/tests/test_browser.py).
- Browser-service logs no longer include proxy URLs, selectors, typed values,
  scripts, destination URLs or raw Playwright exception messages; handled
  startup/navigation/interaction errors use generic messages instead.
  This is not an audit of third-party debug output, all unhandled exceptions or
  logging elsewhere in the application. [Browser logging](../backend/app/browser.py).
- Before initial navigation (including screenshot navigation), and for every
  intercepted context request, a conservative HTTP(S) URL check rejects
  credentials, ambiguous syntax, local names and non-public literal addresses;
  DNS lookups reject empty, timed-out or failed responses and any response with
  a non-public address, including mapped IPv4, multicast and shared address space.
  Lookups have a five-second timeout and no application-level DNS cache.
  [URL and DNS checks](../backend/app/browser.py),
  [offline URL/DNS tests](../backend/tests/test_browser.py).

## Firefox backend automation is not a Firefox frontend/PWA setting

`BROWSER_ENGINE=firefox` starts the Firefox build managed by Playwright on the
backend host/container; it does not switch the browser used to open the app,
connect to the user's installed Firefox, alter frontend installation support,
or grant access to an existing personal browsing session.
The backend context's service-worker restriction is separate from a frontend
PWA's own service worker. [Browser implementation](../backend/app/browser.py),
[configuration](../backend/app/config.py).

No evidence in the inspected browser service establishes that Chromium was
selected for surveillance; the observable behavior was a hard-coded headless
Chromium launch and an identifiable `AI-Companion/1.0` user agent.
This review cannot establish anyone's motives, certify browser binaries, or
verify upstream telemetry/retention practices.
[Inspected browser service](../backend/app/browser.py).

Changing engines alone does not remove this application's configured cloud
data flows or its browser automation capabilities.
[LLM service](../backend/app/llm.py), [memory service](../backend/app/memory.py),
[browser service](../backend/app/browser.py).

## Concrete unresolved risks, ordered by priority

### Critical — exposed execution and skill endpoints

`/api/code/execute` and `/api/code/execute/stream` have no route-level
authentication checks; `CodeSandbox` launches Python/Node subprocesses with
only a working directory and timeout, without supplying an isolated environment
or a separate OS/network security boundary.
A working directory is not a filesystem jail: code can read accessible backend
files and inherited environment secrets and make network connections with
backend privileges. [Code routes](../backend/app/main.py),
[subprocess execution](../backend/app/sandbox.py).

`/api/skills` accepts submitted Python code without authentication, writes a
handler and loads it; `SkillManager.load()` executes that module in the backend
process via `exec_module()`. This is more privileged than browser automation
and must not be exposed to untrusted callers.
[Skill routes](../backend/app/main.py), [skill creation/loading](../backend/app/skills.py).

**Recommended before external exposure:** remove/disable public access to these
routes, require authenticated and authorized users, and move any permitted
execution to a separate, hardened, secret-free worker with resource and egress
limits. This patch deliberately does not attempt that architectural rewrite.

### High — demo authentication and missing ownership enforcement

The browser routes have no authentication dependency, and
`/api/auth/demo` publicly issues tokens for a shared demo account.
Chat and several other routes use optional authentication and fall back to that
account; demo credits are seeded and topped up when the balance is low.
Authentication utilities exist, but their existence does not protect these
routes. [Browser/demo/chat routes](../backend/app/main.py),
[demo account and auth helpers](../backend/app/auth.py).

Characters, conversation-history access and memory retrieval are keyed by
character ID rather than an authenticated user's ownership in the inspected
routes and storage implementation; those are not multi-tenant privacy
boundaries. [Routes](../backend/app/main.py),
[database schema](../backend/app/database.py),
[per-character memory collections](../backend/app/memory.py).

The example JWT secret is a known placeholder and is accepted if copied
unchanged; when the secret is empty, `_default_secret()` generates a new secret
on each call rather than caching one, so tokens may fail validation immediately,
not merely after restart. Invalid optional authentication can then fall back
to demo behavior. [Environment example](../.env.example),
[JWT secret generation and optional auth](../backend/app/auth.py).

**Recommended:** remove production demo fallback, enforce route authentication
plus object ownership, use a strong persistent JWT secret, add abuse controls,
and review token revocation/refresh behavior. Do not interpret the login UI as
proof that the API is private.

### High — network filtering is defense in depth, not SSRF containment

The new context route guard covers requests it actually intercepts, including
frames and ordinary subresources; initial navigation also resolves DNS before
launch/use. It does **not** pin a connection to the checked IP or mediate the
browser's entire network stack. [Request guard](../backend/app/browser.py).

Do not assume redirects are covered: the code uses `route.continue_()`, leaves
redirect following to the browser and does not explicitly validate every
redirect hop before connection.
The mocked tests verify handler behavior, not that every engine/version invokes
the handler on every redirect in a real chain.
No post-navigation check could undo a private request already sent.
[Routing implementation](../backend/app/browser.py),
[test scope](../backend/tests/test_browser.py).

Residual attack/compatibility boundaries in this implementation include:

- DNS time-of-check/time-of-use changes and rebinding; browser DNS, proxy DNS
  or local resolver caches may not match the application's lookup.
- Redirect hops not delivered to this handler.
- WebSocket connections, WebRTC, browser-originated background requests, and
  other traffic not mediated by this HTTP request route.
- Public destinations that forward traffic or receive exfiltrated information;
  a public IP is not a trust or consent decision.
- Browser/URL-parser discrepancies, IPv6 translation/routing peculiarities,
  browser vulnerabilities and future changes in address classification.
- Sites requiring service workers, downloads, local names or proxy-only DNS
  can fail under the more conservative policy.

These are deliberately unresolved limits, not a tested exploitation claim;
the service has no connection pinning, dedicated WebSocket policy, egress
firewall or destination allowlist. [Browser implementation](../backend/app/browser.py).

Separately, `tools.read_webpage()` uses HTTPX with `follow_redirects=True`
without the browser URL/DNS guard; protecting Playwright does not protect that
fetch path, arbitrary code or skills. [HTTPX fetch path](../backend/app/tools.py),
[code execution](../backend/app/sandbox.py), [skills](../backend/app/skills.py).

**Recommended:** enforce private/loopback/link-local/metadata and IPv6 policy at
the actual network boundary, with restrictive destination/port allowlists for
sensitive tasks; isolate automation from internal services and secrets.
An operator-controlled proxy must enforce policy at its own DNS/connect step,
not simply receive a prechecked hostname. Treat a proxy operator as a separate
data recipient, not an automatic privacy guarantee.

### High — cloud data flows remain regardless of browser engine

The LLM client targets `https://openrouter.ai/api/v1`, sends system prompts,
recent conversation history, recalled memories and current user text, and can
send supplied images; tool results are serialized back into the follow-up
completion. Therefore browser text/screenshots returned through tools may leave
the backend for model processing. [LLM construction and tool dispatch](../backend/app/llm.py),
[browser tools](../backend/app/tools.py).

Memory storage sends text to the OpenRouter embeddings API and stores original
documents in local ChromaDB; chat also stores messages in SQLite.
Local persistence is not the same as local-only processing or encrypted
storage. [Memory implementation](../backend/app/memory.py),
[chat persistence](../backend/app/llm.py), [database connection](../backend/app/database.py).

STT defaults to local, but cloud mode sends audio to OpenRouter, and the
unauthenticated `/api/config` update can switch `stt_mode`.
TTS sends text to the configured OpenAI-compatible endpoint when enabled.
These paths require separate consent and provider review; Firefox does not
change them. [STT implementation](../backend/app/stt.py),
[runtime config and TTS routes](../backend/app/main.py),
[settings](../backend/app/config.py).

Search uses Tavily or a DuckDuckGo fallback; generated avatars use OpenAI and
the 3D-avatar service has a Ready Player Me endpoint.
This patch does not verify those providers' retention, training use, telemetry
or downstream subprocessors. [Search tools](../backend/app/tools.py),
[avatar generation](../backend/app/avatar_generator.py),
[3D-avatar service](../backend/app/avatar3d_service.py).

**Recommended:** provide clear per-feature outbound-data disclosure and controls;
use non-sensitive test data until provider policies, retention/deletion,
database access and backup encryption are reviewed.

### High — permissive automation lacks an approval gate

The tool dispatcher directly executes model-selected handlers; no approval
transaction is visible between selection and browser actions.
Browser capabilities include clicking, typing, form filling and page JavaScript
execution, although `execute_js` is a service method rather than a dedicated
HTTP route in the reviewed browser route block.
Filling fields can disclose values before a final submit through page scripts,
and a click can itself be consequential.
[Tool execution](../backend/app/llm.py), [browser methods](../backend/app/browser.py),
[browser routes](../backend/app/main.py).

**Required operating policy:** security-sensitive browsing must be explicit.
Do not automatically log in, fill credentials or personal data, submit forms,
make purchases, send messages, change accounts, grant permissions or execute
untrusted page instructions.
Require a reviewed destination, complete action payload and user confirmation
before such actions; do not treat page content or an LLM tool call as approval.
This patch adds **no application-level approval UI or server-side approval
enforcement**, so that remains a blocking follow-up for unattended use.

### Medium/high — leaked browser resources and incomplete session semantics

The browser HTTP handlers and browser tool wrappers each create a new
`BrowserService` without `try/finally: await bs.close()`.
Startup-failure cleanup added here does not clean up successful calls.
Each endpoint also starts a separate context, so a later click/type endpoint
does not continue the preceding navigate endpoint's page.
[Browser HTTP handlers](../backend/app/main.py),
[browser tool wrappers](../backend/app/tools.py).

The navigation delay is per instance, not a global/per-user API limit; repeated
endpoint calls can create processes and bypass aggregate rate limits.
The service's navigation lock does not serialize all actions against concurrent
close/click operations. [Rate limiting and lifecycle](../backend/app/browser.py).

**Recommended:** make one-shot callers close in `finally`, or introduce
authenticated, owner-bound sessions with explicit lifetime, idle expiry,
concurrency limits and per-user quotas. Do not use a global shared page to fix
the session issue, since that would mix users' state.

### Medium/high — deployment and dependency hardening still needed

CORS is hard-coded to wildcard origins with credentials enabled;
`CORS_ORIGINS` in the example is not consumed by the settings/main implementation.
CORS is not authentication and cannot protect non-browser clients.
[CORS middleware](../backend/app/main.py),
[settings](../backend/app/config.py), [environment example](../.env.example).

Both Compose variants publish backend port 8000 on the host, not only through
Caddy; the Dockerfile has no `USER` restriction and Chromium retains
`--no-sandbox` for compatibility.
The previous production startup conflict was corrected by changing the
Dockerfile's exec-form Uvicorn `ENTRYPOINT` to `CMD`, allowing production
Compose's existing command to replace it and omit `--reload`.
The contract is unit-tested, but an actual container startup still needs
validation. [Dockerfile](../backend/Dockerfile),
[development Compose](../docker-compose.yml),
[production Compose](../docker-compose.production.yml),
[Chromium launch](../backend/app/browser.py),
[startup contract test](../backend/tests/test_browser_config.py).

`backend/requirements.txt` includes unpinned `playwright`, `pydantic-settings`,
GPU/speech dependencies and the rest of the full stack.
No additional runtime package was needed for this patch; the DNS logic uses
the standard library. Unpinned installation prevents claiming a reproducible
or vulnerability-scanned browser/runtime build.
[Requirements](../backend/requirements.txt), [imports](../backend/app/browser.py).

**Recommended:** restrict host ingress, isolate the automation worker and
credentials, run with a tested non-root/sandbox configuration, pin and update
dependencies/browser binaries together, review supply-chain controls, and test
deployment health without exposing these routes publicly.

## Configuration and reproduction commands

Run these from the repository root; Firefox is optional and lowercase values
are required. The normal default remains `chromium`.
[Config contract](../backend/app/config.py), [environment example](../.env.example).

```dotenv
# .env
BROWSER_ENGINE=firefox
PROXY_URL=
```

For a manually provisioned backend, install both engines in the same environment
as the Playwright Python package; the Dockerfile does this during image build.
[Dockerfile](../backend/Dockerfile).

```sh
# Setup examples only — NOT executed during this audit:
python -m playwright install --with-deps chromium firefox
# Reverting .env to BROWSER_ENGINE=chromium restores the existing engine.
# Restart/recreate the backend after configuration changes.
```

### Checks actually executed

The browser suite imports only `browser.py` with mocked settings and Playwright and
mocks DNS resolution; no browser, network target, model API or GPU stack is
required. Three real `pydantic-settings` integration tests run when that
package is installed, as it was for the final run; stdlib AST checks also
verify the declared Literal and unchanged default.
The dynamic settings fixture is registered in `sys.modules` before execution,
so Pydantic can resolve postponed `Literal` annotations; a separate fresh-process
test verifies the normal `app.config` import, Chromium default, Firefox environment
override and rejection of an invalid engine.
[Browser tests](../backend/tests/test_browser.py),
[config tests](../backend/tests/test_browser_config.py).

```sh
cd /home/user/workspace/AI_Companion
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend/tests -v
git diff --check

python - <<'PY'
from pathlib import Path
import ast, yaml
root = Path('/home/user/workspace/AI_Companion')
for name in ('backend/app/browser.py', 'backend/app/config.py',
             'backend/tests/test_browser.py', 'backend/tests/test_browser_config.py'):
    ast.parse((root / name).read_text())
    print('Python syntax OK:', name)
for name in ('docker-compose.yml', 'docker-compose.production.yml'):
    doc = yaml.safe_load((root / name).read_text())
    assert 'BROWSER_ENGINE=${BROWSER_ENGINE:-chromium}' in doc['services']['backend']['environment']
    print('Compose YAML parsed:', name)
PY
```

The validation environment was Python 3.14.3, with PyYAML and Pydantic available.
The integrating agent installed `pydantic-settings` with pip before the final
run; Playwright and a Docker executable remained unavailable.
Final full-backend unit result: **39 discovered; 39 passed; 0 skipped**,
in 1.465 seconds.
Normal `app.config` import and validation also passed in a separate manual
Python process from the backend directory.
Syntax and Compose YAML checks passed and `git diff --check` reported no whitespace errors.
The YAML check is a parser-level check, **not** `docker compose config` or a
container build.

Apart from the integrating agent's lightweight settings dependency installation,
no live Chromium/Firefox run, HTTP/DNS probe, container build, model/provider
call, commit, push or deployment was performed as part of these checks.
This review is not a penetration test, third-party telemetry audit or statement
that either engine is an airtight privacy sandbox.

## Follow-up acceptance criteria before sensitive use

1. Authenticated, authorized ownership checks cover sensitive API routes; public
   demo fallback and unauthenticated code/skill execution are disabled.
2. Browser callers guarantee cleanup and do not share state across users.
3. A dedicated worker/network policy blocks private networks and metadata at
   connect time, including redirects, proxy resolution, IPv6 and non-HTTP paths.
4. Consequential browser actions require server-enforced explicit approval.
5. Users can understand/control cloud text, image, audio and memory flows.
6. Real engine tests run in a deliberately isolated environment with disposable
   data: approved local fixtures, controlled redirects/subresources, DNS-change
   cases, proxy failure, timeout/cancellation and both engine launches.
7. The corrected production command is validated in a real container, and
   non-root isolation, dependency pins, ingress and secret handling are reviewed
   separately.
