#!/bin/sh
# Run inside Home Assistant OS's Terminal & SSH add-on.
# Add the existing community Panasonic brand assets without replacing Python code.
set -eu

component=/config/custom_components/panasonic_cc_reliable
source=https://raw.githubusercontent.com/sockless-coding/panasonic_cc/90c653cb1293af3b4eb022ee1dc2071d00f09d17

test -f "$component/manifest.json" || {
    echo "Integraatiota ei löydy: $component" >&2
    exit 1
}

mkdir -p "$component/brand"
for image in icon.png icon@2x.png; do
    curl -fLsS --connect-timeout 15 --max-time 60 \
        "$source/custom_components/panasonic_cc/brand/$image" \
        -o "$component/brand/$image.new"
    mv "$component/brand/$image.new" "$component/brand/$image"
done
curl -fLsS --connect-timeout 15 --max-time 60 "$source/LICENSE" \
    -o "$component/brand/LICENSE.new"
mv "$component/brand/LICENSE.new" "$component/brand/LICENSE"

echo "Panasonic-kuvake asennettu. Home Assistant käynnistetään uudelleen."
ha core restart
