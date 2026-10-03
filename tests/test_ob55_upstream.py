import asyncio
from unittest.mock import AsyncMock

import httpx
import app
from proto import FreeFire_pb2


def framed_login():
    msg = FreeFire_pb2.LoginRes(
        token='synthetic-token',
        lock_region='SG',
        server_url='https://clientbp.ppmainecoonghj.com',
        ttl=28800,
    )
    return bytes(64) + msg.SerializeToString()


def test_installed_ob55_flow_uses_timestamped_binary_login(monkeypatch):
    import ob55_upstream

    monkeypatch.setattr(app, 'get_access_token', AsyncMock(return_value=('fake-token', 'fake-open')))
    monkeypatch.setattr(ob55_upstream.protocol.time, 'time', lambda: 1800000000)

    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, content=framed_login())

    ob55_upstream.install_ob55_upstream(app, async_client_factory=Client)
    app.cached_tokens.clear()
    asyncio.run(app.create_jwt('BD'))

    assert app.cached_tokens['BD']['token'] == 'Bearer synthetic-token'
    assert calls[0][1]['headers']['ReleaseVersion'] == 'OB55'
    assert calls[0][1]['headers']['X-GA-SV'] == '1800000000'
    assert calls[0][1]['headers']['Content-Type'] == 'application/octet-stream'
    assert 'Authorization' not in calls[0][1]['headers']
