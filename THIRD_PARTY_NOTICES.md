# Third-party notices

The authentication compatibility implementation and public app-protocol constants
in `custom_components/panasonic_cc_reliable/vendor` are adapted from:

- Project: [aio-panasonic-comfort-cloud](https://github.com/sockless-coding/aio-panasonic-comfort-cloud)
- Author: Jimmy Everling / sockless-coding
- Commit: `89bc6f608fab2268e39ca8699878542569f8f9c3`
- License: MIT
- Copyright: (c) 2020-2025 Jimmy Everling

The complete upstream license is included at
[`custom_components/panasonic_cc_reliable/vendor/LICENSE`](custom_components/panasonic_cc_reliable/vendor/LICENSE).
Local adaptations remove sensitive logging, use secure PKCE randomness,
correct CSRF cookie value handling, join relative redirects, use epoch timestamps,
use private account-specific token persistence and bound HTTP access.

API endpoint shapes and enum mappings were researched from the same source and
[sockless-coding/panasonic_cc](https://github.com/sockless-coding/panasonic_cc).
This project credits that community research and does not claim to have newly
reverse-engineered the entire Comfort Cloud protocol.

The Panasonic Comfort Cloud brand images in
`custom_components/panasonic_cc_reliable/brand` are copied unchanged from
[sockless-coding/panasonic_cc](https://github.com/sockless-coding/panasonic_cc),
commit `90c653cb1293af3b4eb022ee1dc2071d00f09d17`. That project's MIT license
(Copyright (c) 2020-2024 Jimmy Everling) is retained in `brand/LICENSE`.
Panasonic names and marks remain the property of their respective owners;
their inclusion does not imply affiliation or endorsement.

The new integration, transport, coordinators, entities, tests and documentation
are MIT-licensed under the repository's `LICENSE`.
