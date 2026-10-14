# Panasonic Comfort Cloud Reliable v0.1.1

An experimental Home Assistant integration featuring **Panasonic Comfort Cloud's own energy consumption data**, vertical/horizontal swing and cloud diagnostics.

## Panasonic's own energy monitoring

- **Energy today** reads the daily kWh value directly from Panasonic's cloud history API. An external electricity meter is not required to retrieve this value.
- **Heating electricity today** and **Cooling electricity today** allocate that daily total using valid mode fractions reported by Panasonic. Missing or ambiguous fractions leave those entities unavailable.
- Panasonic describes the Comfort Cloud figures as [estimated consumption](https://www.panasonic.com/global/hvac-cc/products/comfort-cloud/how-to-use-comfort-cloud/check-air-conditioner-energy-consumption.html). They may be delayed, depend on model support and can represent a shared multi-split system total. These are electrical input figures; live watts, heat output and COP are not inferred.
- Enable **AC energy history** in integration options; the default fetch interval is 15 minutes. Energy failures do not interrupt the other device entities. Energy retrieval is implemented for supported AC / air-to-air heat pumps in this release.

## Included

- Vertical and horizontal swing on the climate entity and separate Select entities.
- Indoor/outdoor temperatures, setpoint, fan setting, operating mode, quiet/powerful preset and unit-on entities.
- Optional AC controls and additional raw numeric sensors where supported by the device response.
- Serialized cloud requests, bounded read retries, token refresh, per-device failure handling and freshness diagnostics.
- Energy timezone correction for Europe/Helsinki and other configured zones, including daylight saving changes.
- Standard and high-resolution Panasonic integration icons.

## Install

Requires Home Assistant Core **2026.10.1 or later**. Add `https://github.com/artepe/panasonic-comfort-cloud-reliable` as an Integration custom repository in HACS, download and restart Home Assistant. For a manual install, extract `panasonic_cc_reliable.zip` into `/config` so the component resides at `/config/custom_components/panasonic_cc_reliable`.

Add **Panasonic Comfort Cloud Reliable** under Settings → Devices & services. Existing users can update the component and restart without removing the integration. Enable energy history and AC controls separately in integration options.

## Validation and attribution

96 automated tests passed against Home Assistant 2026.10.1 using synthetic responses. A user screenshot shows populated temperature and operating-state entities. Live energy availability after the timezone fix and execution of AC commands are still awaiting appliance confirmation. Comparative reliability has not been measured; this is an experimental prerelease.

Built on the MIT-licensed protocol/authentication work of Jimmy Everling / sockless-coding, with licenses and attribution retained. This project is not affiliated with Panasonic.
