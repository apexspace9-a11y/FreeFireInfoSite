import pytest
import protocol
from proto import FreeFire_pb2


def framed(**changes):
    values = dict(
        token='synthetic-token',
        lock_region='SG',
        server_url='https://clientbp.ppmainecoonghj.com',
        ttl=28800,
    )
    values.update(changes)
    return bytes(64) + FreeFire_pb2.LoginRes(**values).SerializeToString()


def test_versioned_timestamp(monkeypatch):
    monkeypatch.setattr(protocol.time, 'time', lambda: 1800000000)
    assert protocol.binary_headers('OB55')['X-GA-SV'] == '1800000000'
    assert 'X-GA-SV' not in protocol.binary_headers('OB54')


def test_ob55_framing_and_legacy():
    body = framed()
    assert protocol.decode_login(body, 'OB55').token == 'synthetic-token'
    assert protocol.decode_login(body[64:], 'OB54').ttl == 28800


@pytest.mark.parametrize('body', [b'', bytes(64), bytes(64) + b'\xff', b'<html>503</html>'])
def test_malformed_login(body):
    with pytest.raises(protocol.UpstreamError):
        protocol.decode_login(body, 'OB55')


def test_legacy_queue_not_a_token():
    msg = FreeFire_pb2.LoginRes()
    msg.queue_info.allow = True
    with pytest.raises(protocol.UpstreamError) as error:
        protocol.decode_login(msg.SerializeToString(), 'OB54')
    assert error.value.code == 'LOGIN_QUEUE'
    assert error.value.status == 503


@pytest.mark.parametrize('url', [
    'http://clientbp.ppmainecoonghj.com',
    'https://example.com',
    'https://clientbp.ppmainecoonghj.com@evil.example',
    'https://clientbp.ppmainecoonghj.com/x',
    'https://clientbp.ppmainecoonghj.com?token=secret',
])
def test_untrusted_server(url):
    with pytest.raises(protocol.UpstreamError):
        protocol.decode_login(framed(server_url=url))


def test_missing_token():
    with pytest.raises(protocol.UpstreamError) as error:
        protocol.decode_login(framed(token=''))
    assert error.value.code == 'INCOMPLETE_LOGIN'


@pytest.mark.parametrize('timestamp', [1756478597, 1766375816])
def test_ob55_field13_is_not_assumed_to_be_queue(timestamp):
    msg = FreeFire_pb2.LoginRes()
    msg.queue_info.allow = True
    msg.queue_info.need_wait_secs = timestamp
    with pytest.raises(protocol.UpstreamError) as error:
        protocol.decode_login(bytes(64) + msg.SerializeToString(), 'OB55')
    assert error.value.code == 'UNRECOGNIZED_LOGIN_RESPONSE'
    assert str(timestamp) not in str(error.value)
