# Protocol observations and provenance

Reviewed on 2026-10-13:

- `sockless-coding/aio-panasonic-comfort-cloud`, commit `89bc6f608fab2268e39ca8699878542569f8f9c3`.
- `sockless-coding/panasonic_cc`, commit `90c653cb1293af3b4eb022ee1dc2071d00f09d17`.
- Home Assistant's current config-flow, setup-failure and coordinator documentation; implementation validated with Core 2026.10.1.

These observations come from public community source code, not a newly captured official-app session. No user's password, token, packet capture or live appliance data was used for development.

## Observed endpoints

All API routes below are relative to `https://accsmart.panasonic.com`.

| Route | Method | Observed purpose | This project's policy |
| --- | --- | --- | --- |
| `/auth/v2/login` | POST | Register an Auth0 access token and obtain `clientId` | Account-specific; only during login/session repair |
| `/device/group` | GET | Device discovery and HWS listing status | Shared discovery; no speculative AC requests for HWS |
| `/deviceStatus/{guid}` | GET | AC live status | Preferred read |
| `/deviceStatus/now/{guid}` | GET | AC cloud-cached status | Only after a communication failure; explicitly labeled |
| `/deviceStatus/control` | POST | AC parameter write | Never replayed after timeout/rejection |
| `/deviceHistoryData` | POST | AC history | Read-only POST; separately paced and optional |
| `/remote/v1/app/common/transfer` | POST | Aquarea API proxy | Status reads only in 0.1.0 |

An Aquarea status request wraps `/remote/v1/api/devices?gwid=...&deviceDirect=1` with `requestMethod: GET`. Its cached variant uses `deviceDirect=0`. Aquarea status/control enum values differ, so this version does not reuse AC write mappings for Aquarea.

The source also describes Aquarea consumption, weekly timers and some HWS-specific endpoints. They are not enabled here merely because a route string exists. First verify real response shapes and supported semantics before adding actions.

## Authentication/signing

The adapted upstream login uses Panasonic's Auth0 hosted flow, authorization code with PKCE, refresh tokens and supported classic/Guardian MFA challenges. Authentication requests have finite timeouts and a private cookie jar. Dynamic sign-in destinations must remain HTTPS Panasonic hosts. The public app client ID and request-signing seed are protocol constants, not this user's secrets.

API headers include app version, timestamp, `x-user-authorization-v2`, `x-client-id` and the community-discovered SHA-256 signature format. Timestamps are generated in UTC consistently with signing. App version is explicit and configurable; no store-scraping fallback exists.

Authentication failures, version mismatch (4106), updated agreements (4103), rate limits and adapter/cloud communication failures are different typed errors. A generic HTTP 403 does not automatically mean the password is wrong.

## Further research

1. Run monitoring on an account authorized for your appliance.
2. Compare the redacted diagnostic response with the official app's visible values.
3. Record field presence, missing-value sentinels, scale, units and whether changes are live or cached.
4. Add an anonymized fixture and a semantic test before adding a named sensor.
5. For commands, document the exact request and supported models, validate bounds and never retry a delivery-uncertain write.

Do not commit account tokens, passwords, raw packet captures, device GUIDs or customer configuration. This project's diagnostics are a starting point for review, not proof that every unknown field is safe or understood.
