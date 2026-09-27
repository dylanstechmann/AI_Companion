# Authentication and trusted accounts

Operational API routes require an `Authorization: Bearer <access_token>` header.
This includes chat and code streams, browser controls, skills, character history,
configuration, credit operations, and notification subscriptions. The frontend
sends the token through its shared API client and refreshes an expired access
token once. Sessions are retained in sessionStorage for the current browser tab;
Sign out clears that tab's credentials. Existing stateless tokens remain valid
until expiration; this change does not implement server-side token revocation.

This is a shared instance for trusted operators. Registered users can run code,
load Python skills in the backend process, and access shared characters and
conversation history. Authentication does not provide per-user data isolation
or a sandbox for untrusted code. Do not invite untrusted users.

## Create the first account locally

1. Copy `.env.example` to `.env` and generate a JWT secret, for example with
   `python -c "import secrets; print(secrets.token_hex(32))"`. Save it in `.env`.
2. Keep `APP_ENV=development` and set `ALLOW_REGISTRATION=true` temporarily.
   The development Compose file publishes ports on 127.0.0.1 only.
3. Start the development app, open http://localhost:3000, select Register, and
   create your account. Registration returns the same token/user shape as login.
4. Set `ALLOW_REGISTRATION=false` and recreate the backend. Existing accounts
   can still log in. Keep `ALLOW_DEMO_LOGIN=false` for ordinary use.

Setting `ALLOW_DEMO_LOGIN=true` explicitly enables a shared development demo
account with operational access. It is never selected automatically. Disabling
it also rejects access/refresh tokens previously issued for that demo account.

## Production

The production Compose file sets `APP_ENV=production` and disables registration
and demo access. Startup fails without a generated JWT secret of at least 32
characters; short or example placeholder keys are rejected in every mode.
Use the same secret for all backend workers and replicas. A blank development
secret is generated once per process and tokens stop working after restart.

Protect remote access with HTTPS. The public API exceptions are health, enabled
login/bootstrap endpoints, credit-pack metadata, the VAPID public key, and payment
webhooks. Webhooks retain their separate provider verification; this auth change
does not audit or harden payment processing. Generated `/api/avatars` images and
API documentation remain public assets.

## Verification

The regression suite exercises the real FastAPI routes, JWT implementation and
a temporary SQLite database. It replaces the unrelated LLM, memory and research
service imports so it needs no GPU, models, provider keys, or live payments.

From `backend`, install `requirements-test.txt`, then run
`python -B -m unittest discover -s tests -v`. From `frontend`, run
`npm test` and `npm run build`. Use the shared workspace dev container for these
commands when working in the parent workspace.
