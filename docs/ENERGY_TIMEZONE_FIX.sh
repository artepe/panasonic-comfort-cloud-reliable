#!/bin/sh
# Apply only the energy offset fix to an installed 0.1.0/0.1.1 component.
# The complete updated ZIP also includes the expanded energy diagnostics.
(
  set -e
  if [ -f /homeassistant/custom_components/panasonic_cc_reliable/api.py ]; then
    FILE=/homeassistant/custom_components/panasonic_cc_reliable/api.py
  elif [ -f /config/custom_components/panasonic_cc_reliable/api.py ]; then
    FILE=/config/custom_components/panasonic_cc_reliable/api.py
  else
    echo "Integraation api.py-tiedostoa ei löytynyt."
    exit 1
  fi
  if grep -Eq 'comfort_cloud_timezone|timezone = offset' "$FILE"; then
    echo "Aikavyöhykekorjaus on jo asennettu."
    exit 0
  fi
  if ! grep -Fq '    async def energy(self, device: Device, day: str, timezone: str) -> dict:' "$FILE"; then
    echo "Odottamaton tiedostoversio. Käytä korjattua ZIP-pakettia."
    exit 1
  fi
  if [ ! -f "$FILE.energy.bak" ]; then
    cp "$FILE" "$FILE.energy.bak"
  fi
  sed -i '/^    async def energy(self, device: Device, day: str, timezone: str) -> dict:$/a\
        from datetime import datetime\
        from zoneinfo import ZoneInfo\
        offset = datetime.now(ZoneInfo(timezone)).strftime("%z")\
        timezone = offset[:3] + ":" + offset[3:]
' "$FILE"
  ha core restart
)
