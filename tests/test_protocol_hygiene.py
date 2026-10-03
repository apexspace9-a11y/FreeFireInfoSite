from datetime import datetime, timezone

import protocol_hygiene


def test_current_event_time_replaces_legacy_constant():
    fixed = datetime(2026, 10, 3, 12, 34, 56, tzinfo=timezone.utc)
    assert protocol_hygiene.current_event_time(fixed) == "2026-10-03 12:34:56"
    assert protocol_hygiene.current_event_time(fixed) != "2025-05-29 13:11:47"


def test_patch_only_changes_legacy_event_time_field():
    calls = []

    class FakeApp:
        @staticmethod
        def _pb_bytes(field, value):
            calls.append((field, value))
            return f"{field}:{value}".encode()

    protocol_hygiene.install_live_timestamp(FakeApp, now_factory=lambda: datetime(2026, 10, 3, 12, 34, 56, tzinfo=timezone.utc))

    result = FakeApp._pb_bytes(3, "2025-05-29 13:11:47")
    assert result == b"3:2026-10-03 12:34:56"

    untouched = FakeApp._pb_bytes(25, "realme RMX1825")
    assert untouched == b"25:realme RMX1825"
