"""Integration configuration."""

DOMAIN = "panasonic_cc_reliable"
NAME = "Panasonic Comfort Cloud Reliable"
VERSION = "0.1.1"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ENERGY_INTERVAL = "energy_interval"
CONF_ENABLE_ENERGY = "enable_energy"
CONF_STALE_AFTER = "stale_after"
CONF_APP_VERSION = "app_version"
CONF_RAW_SENSORS = "raw_sensors"
CONF_ENABLE_CONTROL = "enable_control"
DEFAULTS = {
    CONF_POLL_INTERVAL: 120,
    CONF_ENERGY_INTERVAL: 900,
    CONF_ENABLE_ENERGY: False,
    CONF_STALE_AFTER: 600,
    CONF_APP_VERSION: "4.4.0",
    CONF_RAW_SENSORS: False,
    CONF_ENABLE_CONTROL: False,
}
BASE_URL = "https://accsmart.panasonic.com"
MIN_REQUEST_GAP = 1.0
MAX_BACKOFF = 1800
