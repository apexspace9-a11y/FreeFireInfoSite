from datetime import datetime, timezone

import direct_profile


def test_build_plain_major_login_uses_current_timestamp_and_no_fake_device_defaults():
    fixed_now = datetime(2026, 10, 3, 12, 34, 56, tzinfo=timezone.utc)
    packet = direct_profile.build_plain_major_login(
        open_id="open-id",
        access_token="token",
        guest_uid="12345",
        client_version="1.132.1",
        now=fixed_now,
    )

    assert b"2026-10-03 12:34:56" in packet
    assert b"2025-05-29 13:11:47" not in packet
    assert b"realme RMX1825" not in packet
    assert b"182.75.115.22" not in packet
    assert b"base.apk" not in packet
    assert b"open-id" in packet
    assert b"token" in packet
    assert b"12345" in packet


def test_optional_client_metadata_only_appears_when_explicitly_configured():
    fixed_now = datetime(2026, 10, 3, 12, 34, 56, tzinfo=timezone.utc)
    packet = direct_profile.build_plain_major_login(
        open_id="open-id",
        access_token="token",
        guest_uid="12345",
        client_version="1.132.1",
        now=fixed_now,
        system_software="Android OS 13 / API-33",
        device_model="CPH2095",
        network_type="WIFI",
        locale="en",
    )

    assert b"Android OS 13 / API-33" in packet
    assert b"CPH2095" in packet
    assert b"WIFI" in packet
    assert b"en" in packet
