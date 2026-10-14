# Data fields

Mappings reflect the reviewed community client. None has been independently verified on the user's appliance in this release.

| Device family | Field | Exposed interpretation |
| --- | --- | --- |
| AC | `parameters.insideTemperature` | Indoor °C; impossible/sentinel values become unknown |
| AC | `parameters.outTemperature` | Outdoor °C when supplied |
| AC | `parameters.temperatureSet` | Confirmed target °C |
| AC | `parameters.operate`, `operationMode` | Power/selected HVAC mode, not actual compressor activity |
| AC | `parameters.airQuality` | Raw model-dependent code; disabled diagnostic sensor |
| AC history | Today's row in `historyDataList`, `consumption` | Panasonic's daily kWh estimate/total; no wattage derived from sparse history |
| Aquarea | `status.outdoorNow` | Outdoor °C |
| Aquarea | `status.zoneStatus[].temperatureNow` | Zone sensor value; could represent room/water temperature |
| Aquarea | `status.zoneStatus[].heatSet`, `coolSet` | Zone heating/cooling targets |
| Aquarea | `status.tankStatus.temperatureNow`, `heatSet` | Tank temperature and target |
| Aquarea | `status.deiceStatus` | Defrost flag if a recognized 0/1 is supplied |
| Aquarea | `status.forceDHW`, `forceHeater`, `pumpDuty` | Reported flags, without implying measured electrical power |
| Aquarea | `status.waterPressure` | Unscaled raw value; no bar/kPa unit assumed |
| HWS | `parameters.tankTemperature` | Configurable tank setpoint from listing, not assumed actual water temperature |
| HWS | `parameters.boostMode`, `operationMode` | Raw appliance operating codes |
| All | `timestamp` where supplied | Cloud timestamp displayed separately; exact update semantics unverified |

Extra raw sensors expose only numeric leaves under the device's `parameters` or `status`. They are disabled initially and do not make additional API calls. Text, tokens and recognized identifying keys are excluded.

No physical sensor is fabricated to fill a gap. If a raw response contains a promising field, validate it on the real model before giving it a public engineering name or unit. Availability and connection diagnostics describe what this integration knows, not a guarantee of Panasonic device connectivity.
