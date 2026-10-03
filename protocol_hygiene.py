from datetime import datetime, timezone


LEGACY_EVENT_TIME = "2025-05-29 13:11:47"


def current_event_time(now=None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def install_live_timestamp(app_module, now_factory=None):
    """Replace only the stale hard-coded MajorLogin event timestamp.

    All other protobuf fields, headers, credentials, retry behavior, and
    client metadata remain unchanged.
    """
    original_pb_bytes = app_module._pb_bytes
    factory = now_factory or (lambda: datetime.now(timezone.utc))

    def pb_bytes(field, value):
        if field == 3 and value == LEGACY_EVENT_TIME:
            value = current_event_time(factory())
        return original_pb_bytes(field, value)

    app_module._pb_bytes = pb_bytes
    app_module.MAJOR_LOGIN_TIMESTAMP_MODE = "live-utc"
    return pb_bytes
