# Panasonic Comfort Cloud Reliable

An experimental Home Assistant integration with **Panasonic Comfort Cloud's own energy consumption data**, swing controls, conservative polling and inspectable diagnostics.

**Version 0.1.1 is a research/alpha release. It has automated tests against Home Assistant 2026.10.1 and synthetic responses. A user screenshot shows populated temperature and operating-state entities; energy availability and command execution have not yet been confirmed on the appliance. The name describes the design goal, not a measured reliability advantage over another integration.**

This project uses the community's reverse-engineered Comfort Cloud protocol. Its transport, coordinator, models and Home Assistant entities are new code. The login/MFA compatibility implementation is adapted from [Jimmy Everling / sockless-coding's MIT-licensed client](https://github.com/sockless-coding/aio-panasonic-comfort-cloud), with its copyright and license retained. It does not depend on that library at runtime. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Panasonic's own energy monitoring

**Daily electricity consumption comes directly from Panasonic Comfort Cloud's energy history API.** The integration exposes Panasonic's daily `consumption` value in kWh. No external electricity meter is needed to retrieve this cloud value.

| Entity | Data source |
| --- | --- |
| Energy today | Today's kWh value returned by Panasonic's `deviceHistoryData` endpoint |
| Heating electricity today | Daily kWh multiplied by a valid heating fraction supplied by Panasonic |
| Cooling electricity today | Daily kWh multiplied by a valid cooling fraction supplied by Panasonic |

Panasonic describes its own [Comfort Cloud energy consumption figures](https://www.panasonic.com/global/hvac-cc/products/comfort-cloud/how-to-use-comfort-cloud/check-air-conditioner-energy-consumption.html) as **estimates**. Values can arrive with a delay, and availability depends on the appliance and the cloud response. The integration preserves that distinction: these values represent electrical input, with no live watts, thermal output or COP inferred. Heating/cooling allocations remain unavailable if the reported fractions are missing or ambiguous. Multi-split installations can report a shared system total for each indoor unit; avoid summing those duplicate totals.

Enable **AC energy history** in integration options. It is off by default and refreshes every 15 minutes when enabled. Missing history leaves energy entities unavailable without interrupting temperature readings or climate controls. Energy retrieval currently applies to supported AC / air-to-air heat pump devices; Aquarea and standalone HWS energy are not implemented in this release. The current user's live energy result still needs confirmation after the timezone fix.

## Energy hotfix, 2026-10-14

The updated 0.1.1 package fixes the energy request timezone: `osTimezone` now contains a signed offset (`+03:00`, `+02:00`, etc.), derived from HA’s configured timezone rather than the server’s local timezone. It handles seasonal DST changes. Energy diagnostics now include the attempted date/offset, attempt time, HTTP error information and returned day identifiers. JSON integer day identifiers are accepted as well as strings.

Existing accounts and entity identities are retained. [ENERGY_TIMEZONE_FIX.sh](docs/ENERGY_TIMEZONE_FIX.sh) applies just the timezone correction to an existing installation; installing the full updated ZIP also adds the expanded diagnostics. Live energy availability still requires a device test.

## Changes in 0.1.1

- Bundled Panasonic Comfort Cloud integration icon in standard and high-resolution sizes. Home Assistant serves it from the component's `brand` directory. [ICON_INSTALL.sh](docs/ICON_INSTALL.sh) adds only these assets to an existing HA OS installation.
- Vertical and horizontal swing on the climate entity as well as separate Select entities, preserving the other axis's auto setting.
- Operating mode, fan setting, comfort preset and unit-on entities.
- Daily heating/cooling electricity allocation when the history response supplies valid 0–1 fractions. Missing or ambiguous rates leave the allocation unavailable. These are electrical input, not thermal output.
- Corrected default app version 4.4.0 and a version field during initial sign-in.

After updating, enable **AC controls** and **AC energy history** in integration options to expose the controls and energy entities. Energy history defaults to a 15-minute interval and can take at least one successful history fetch to appear. Existing account/entity identities are preserved.

## What this release supports

| Device | Monitoring | Controls |
| --- | --- | --- |
| Comfort Cloud air conditioner / air-to-air heat pump | Indoor/outdoor temperature, confirmed setpoint, connection diagnostics, optional daily energy, additional raw fields | Experimental power, supported HVAC modes, 16–30 °C setpoint, fan, quiet/powerful, vanes and compatible Nanoe on/off |
| Aquarea air-to-water heat pump | Outdoor temperature, tank and zone values, reported defrost/forced-DHW/backup-heater/pump flags, raw status fields | Read-only in 0.1.1 |
| Standalone HWS hot water heat pump (`deviceType: 11`) | Group-listing fields and diagnostics; no AC status requests | Read-only in 0.1.1 |
| Unknown device types | Identified in diagnostics | Unsupported |

Fields and controls appear only when the device response supports them. A missing temperature is unknown, not zero. Unmapped numeric fields have no guessed unit or engineering meaning. Aquarea zone values can mean room temperature or water temperature depending on controller configuration. No compressor frequency, refrigerant pressure, thermal output or COP sensor is invented.

Monitoring is enabled by default. AC commands require explicitly enabling **Enable experimental AC controls** in the integration's options.

## Reliability mechanisms

- One serialized request queue, token lifecycle and private cookie jar per account.
- Access tokens refresh before expiry; the earliest available expiry wins.
- Rotated refresh tokens use Home Assistant's private, atomic Store, including when subsequent registration fails. Passwords and one-time codes are never persisted.
- Cloud requests have a 30-second timeout. A read gets at most three attempts, with bounded jittered delays. A write is sent once; a timeout produces an uncertain-delivery error rather than silently repeating it.
- HTTP 429 and `Retry-After` apply to the whole account. Device failures get independent exponential backoff; a broken device does not discard another device's data.
- Energy history is optional, slower and independent from temperatures/control status. History errors do not make climate entities unavailable.
- Last confirmed values survive brief errors, with connection/failure/last-fetch attributes. Primary entities become unavailable once the configured age limit is reached. This is not a persistent offline cache after restart.
- Cached endpoint responses are labeled. They require a recent cloud timestamp to be considered usable and never authorize commands. The meaning of Panasonic's timestamp is not independently verified; it is displayed separately from fetch time.
- Successful writes request another status read. No optimistic state or inferred compressor-running state is reported.
- Reauthentication uses Home Assistant's normal flow and preserves entity identity. Extra devices and fields can be discovered later without reinstalling.
- Debug diagnostics exclude authentication state and recursively redact account/device identifiers. No request body, credential, response HTML or authorization redirect is logged by the adapted login code.

These measures cannot eliminate Panasonic service outages, revoked sessions, changed login pages, MFA changes or undocumented API changes. Account/app contention may still occur. If available, share appliances with a separate Home Assistant Panasonic account rather than simultaneously running multiple integrations against the same account.

## Installation

Requires Home Assistant **2026.10.1 or later**. This is the version used for local validation; newer releases still need their own testing. Raspberry Pi 5 / Home Assistant OS can run it like other custom integrations.

### HACS custom repository

1. Open HACS → menu → **Custom repositories**.
2. Add `https://github.com/artepe/panasonic-comfort-cloud-reliable` as an **Integration** repository.
3. Download and restart Home Assistant.
4. Settings → Devices & services → Add integration → **Panasonic Comfort Cloud Reliable**.
5. Enter your Panasonic ID and password inside Home Assistant. Complete a one-time verification challenge if requested. Do not put passwords, codes or tokens in GitHub issues.

This project is a custom repository; it is not listed in HACS's default catalog.

### Manual

Copy `custom_components/panasonic_cc_reliable` to `/config/custom_components/panasonic_cc_reliable`, restart Home Assistant and add it through Devices & services. Keep the complete `vendor` and `translations` directories.

The domain is different from `panasonic_cc`, so files and entities do not overwrite the original integration. Disable its polling during this project's test to avoid competing requests.

## Recommended first test

1. Confirm that the official Comfort Cloud app can access the appliance and that required MFA/agreements have been completed there.
2. Disable the old integration's polling. Keep this integration in monitoring mode.
3. Use the defaults: 120-second status polling, 600-second maximum age, energy off.
4. Compare reported values with the official app. Inspect **Connection status**, **Data source**, **Last successful fetch** and **Cloud timestamp**.
5. Enable **Discover extra raw numeric sensors** if investigating additional data. These entities start disabled: enable selected ones in Settings → Devices & services → Entities. Never assign a unit based only on a field name.
6. Download integration diagnostics from the entry's menu. Review the export before sharing it. It includes redacted raw listing/status shapes useful for adding real measurements.
7. After monitoring works, optionally enable AC controls and test one ordinary action. Aquarea and HWS remain read-only.

There is no 1-second cloud-polling option. The refresh button respects cooldowns/backoff and refreshes the shared account, not just one entity.

## Options

| Setting | Default | Allowed range / effect |
| --- | --- | --- |
| Status interval | 120 s | 60–1800 s |
| Maximum status age | 600 s | 120–7200 s; at least twice the polling interval |
| Energy history | Off | AC only; delayed/estimated daily kWh, not live watts |
| Energy interval | 900 s | 600–7200 s |
| Extra raw numeric sensors | Off | Discover numeric status leaves; disabled initially, no assumed units |
| Experimental AC controls | Off | Enable AC actions after validating monitoring |
| App protocol version | `4.4.0` | Explicit version header checked against the official App Store listing on 2026-10-13; may need updating if Panasonic returns 4106 |

The integration does not scrape app stores or silently accept updated legal agreements. For error 4103, review the updated documents in the official app. For 4106, update the version only after checking the currently required app protocol.

## Developing and reverse engineering

See [Protocol notes](docs/PROTOCOL.md), [Finnish installation guide](docs/ASENNUS_FI.md), [Data field notes](docs/DATA.md) and [Validation](docs/VALIDATION.md).

```bash
uv venv --python 3.14
uv pip install --python .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Tests use synthetic appliance identifiers and mocked responses. They must never contact a Panasonic account. GitHub Actions runs tests and static checks; HACS validation also needs the repository to exist on GitHub. After the automated checks pass, the release workflow packages and publishes an experimental prerelease when a `v*` tag is pushed.

This project is not affiliated with Panasonic. Comfort Cloud remains a cloud dependency. Licensed community protocol research is credited rather than presented as a newly discovered proprietary protocol.
