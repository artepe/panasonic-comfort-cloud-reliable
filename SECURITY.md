# Security policy

## Reporting a vulnerability

Please do not report security problems in public issues. Use GitHub's private vulnerability reporting (**Security → Report a vulnerability** on this repository) or contact the maintainer privately through the GitHub profile [@artepe](https://github.com/artepe). Please allow time for a fix before publishing details.

## Supported versions

Security fixes are made to the latest release and the `main` branch only.

## Security design

- The Panasonic password is used only during setup and reauthentication and is never stored. Session tokens are kept in Home Assistant private storage, and diagnostics redact authentication data and account identifiers.
- The client honours HTTP 429 `Retry-After`, cools down the account and backs off exponentially to avoid hammering the cloud service.
