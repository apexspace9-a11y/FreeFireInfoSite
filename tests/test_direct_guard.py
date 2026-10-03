import asyncio

import httpx
import pytest

from direct_guard import ABNORMAL_CODE, install_direct_guard


class FakeResponse:
    def __init__(self, status_code, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")


class FakeClient:
    def __init__(self, responses, calls, **kwargs):
        self.responses = list(responses)
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, data=None, headers=None):
        self.calls.append(url)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeApp:
    class UpstreamAPIError(RuntimeError):
        pass

    RELEASEVERSION = "OB55"
    CLIENT_VERSION = "1.132.1"
    UNITY_VERSION = "2018.4.12f1"
    GA_SERVER_VERSION = "1789534056"
    MAJOR_LOGIN_URL = "https://primary.example/MajorLogin"
    MAJOR_LOGIN_FALLBACK_URLS = [
        "https://fallback-1.example/MajorLogin",
        "https://fallback-2.example/MajorLogin",
    ]
    cached_tokens = {}

    @staticmethod
    def get_account_credentials(region):
        return "uid=123&password=abc"

    @staticmethod
    async def get_access_token(account):
        return "access-token", "open-id"

    @staticmethod
    def build_ob55_major_login_payload(open_id, access_token, guest_uid):
        return b"payload"

    @staticmethod
    def decode_major_login_wire(raw):
        return {
            "token": "eyJ.test",
            "serverUrl": "https://player.example",
            "lockRegion": "BD",
            "ttl": 25200,
        }

    @staticmethod
    def _short_upstream_error(exc):
        return str(exc)[:240]


def test_abnormal_client_stops_after_first_gateway():
    calls = []
    responses = [FakeResponse(400, ABNORMAL_CODE)]

    def factory(**kwargs):
        return FakeClient(responses, calls, **kwargs)

    install_direct_guard(FakeApp, async_client_factory=factory)

    with pytest.raises(FakeApp.UpstreamAPIError) as exc_info:
        asyncio.run(FakeApp.create_jwt("BD"))

    assert ABNORMAL_CODE in str(exc_info.value)
    assert calls == [FakeApp.MAJOR_LOGIN_URL]


def test_transport_error_can_still_use_garena_gateway_fallback():
    calls = []
    responses = [
        httpx.ConnectError("temporary connect failure"),
        FakeResponse(200, content=b"ok"),
    ]

    def factory(**kwargs):
        return FakeClient(responses, calls, **kwargs)

    FakeApp.cached_tokens = {}
    install_direct_guard(FakeApp, async_client_factory=factory)
    asyncio.run(FakeApp.create_jwt("BD"))

    assert calls == [
        FakeApp.MAJOR_LOGIN_URL,
        FakeApp.MAJOR_LOGIN_FALLBACK_URLS[0],
    ]
    assert FakeApp.cached_tokens["BD"]["token"] == "Bearer eyJ.test"
