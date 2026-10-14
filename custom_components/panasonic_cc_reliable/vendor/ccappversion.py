"""An explicit protocol version instead of scraping an app store."""

from ..errors import AppVersionError


class CCAppVersion:
    def __init__(self, version: str):
        self.version = version

    async def get(self) -> str:
        return self.version

    async def refresh(self) -> None:
        raise AppVersionError("Update the app version in integration options", code=4106)
