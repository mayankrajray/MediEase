"""M7e-E5: ``make vapid-keys`` prints a pair the settings and the push adapter accept."""

from __future__ import annotations

import io

from mediease_api.adapters.push.webpush import PyWebPushAdapter
from mediease_api.delivery.cli import vapid_keys


def test_m7e_e5_the_printed_pair_is_valid_and_new_each_time() -> None:
    out = io.StringIO()
    assert vapid_keys.main(out) == 0
    lines = dict(
        line.split("=", 1) for line in out.getvalue().splitlines() if not line.startswith("#")
    )
    public, private = lines["VAPID_PUBLIC_KEY"], lines["VAPID_PRIVATE_KEY"]
    assert (len(public), len(private)) == (87, 43)
    # The adapter refuses a mismatched pair at start-up; this one it accepts.
    PyWebPushAdapter(private_key=private, public_key=public, subject="mailto:push@example.test")
    assert vapid_keys.new_pair() != (public, private)
