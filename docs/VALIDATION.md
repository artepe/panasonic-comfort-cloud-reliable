# Validation of 0.1.1

Local validation updated on 2026-10-14.

| Check | Result |
| --- | --- |
| Automated suite | 96 passed |
| Python | CPython 3.14.8 |
| Home Assistant | Core 2026.10.1 |
| Ruff static checks | Passed |
| Ruff formatting | Passed |
| Python bytecode compilation | Passed |
| Manifest, translations and workflow file parsing | Passed |
| Real HA loader/platform smoke test, simulated device | Passed: climate/sensor entities registered, setup/unload and config-flow registration checked |
| Classic login, OTP and Guardian login protocol fixtures | Passed with scripted synthetic responses |
| Live Panasonic sign-in, real MFA/SMS, real appliance and command confirmation | **Not performed** |
| User installation screenshot | Populated indoor/outdoor temperature, setpoint and operating-state entities observed; energy unavailable in that screenshot, recovery after the timezone fix unconfirmed |
| Comparative reliability versus another integration | **Not measured** |
| HACS remote validation and GitHub Actions | Requires publication and workflow execution; not a local check |

The test suite covers serialized account access, one refresh for concurrent expired-token reads, earliest-expiry behavior, refresh-token persistence after a registration failure, bounded read retries, non-replayed writes, 429 cooldowns, typed error envelopes, cache fallback boundaries, stale values, device isolation, independent history failures, sentinel values, dynamic discovery, zone reordering, conservative command bounds and reauthentication without saving passwords/codes.

One warning originates from Home Assistant's own HTTP application inheritance of `aiohttp.web.Application`. It is not a failed test or evidence of live API compatibility.

No real credentials or captures were used. Do not treat these tests as proof of appliance support, login compatibility for every MFA enrollment, or improved field reliability. Validate monitoring on the intended model before enabling AC controls.

Initial device testing reported error 4106 with the upstream fallback version 1.21.0. The default is now 4.4.0, checked against Panasonic’s official App Store listing on 2026-10-13. The sign-in form accepts an explicit version and persists it for runtime and reauthentication. This fixes the stale header configuration; live login acceptance of the updated header still needs confirmation.

Version 0.1.1 adds native climate swing controls, unit-on and selected-mode sensors, and electrical heating/cooling allocation from validated cloud fractions. Daily energy uses TOTAL with an explicit local-day reset so cloud corrections are not interpreted as a new meter cycle. The associated synthetic tests cover independent-axis auto mode preservation, unsupported swing choices, missing/ambiguous fraction handling and daily corrections. Live swing execution and live history availability still need the user’s appliance test.

Energy hotfix (2026-10-14): history requests previously sent IANA names such as Europe/Helsinki in osTimezone. The reviewed protocol uses signed UTC offsets. The corrected request derives the offset from HA’s configured zone, including DST, negative and fractional-hour zones. Tests inspect the outgoing history payload, October DST transition, winter/summer offsets and integer day identifiers. Energy attempt time, offset, HTTP error, history count and returned day identifiers are now in diagnostics. User screenshots show device state sensors; the live energy response has not been inspected, so successful energy recovery is still pending the appliance test.
