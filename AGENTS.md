# Agent instructions — AI_Companion

Open this repo only when the user named it. It is a self-hosted voice/memory companion, not part of the regenerative-medicine stack. Do not import hypothesis cards, protocols, or compound scores.

## Do not

- Commit `.env`, API keys, `data/`, or Chroma stores.
- Treat the README roadmap checkboxes as implemented. Read the file before claiming an endpoint exists.
- Widen the code-execution sandbox or bind services off localhost.
- Add medical, dosing, or crisis-counseling behavior. If a user message looks like a crisis, the product should point at local emergency services / 988, not role-play treatment.

## First commands

```bash
test -f .env.example && echo example_present
docker compose config
```

Run the test suite that already exists. Do not invent a greenfield app on top of this one.

## Improve, in this order

1. List README claims that have no corresponding module. Fix the README or implement one missing health/auth check, not both in a vague way.
2. Confirm registration stays off by default and APIs require a bearer token, matching `docs/AUTHENTICATION.md`.
3. One vertical slice per session (health route, or token refresh, or a single test). No Phase 2+3 dump.

## Done when

The change is covered by a test or a documented manual check, and no secret is in the diff.
