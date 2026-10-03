"""Runtime adapter for the upstream FreeFireInfoSite OB55 v2.2 protocol flow.

Keeps this fork's existing credential source and UI/media routes, while using
upstream's verified OB55 request headers, four-field LoginReq and 64-byte login
response framing.
"""
import json
import time

import httpx

import protocol


def install_ob55_upstream(app_module, async_client_factory=httpx.AsyncClient):
    app_module.RELEASEVERSION = protocol.RELEASE_VERSION

    def upstream_error(exc):
        if isinstance(exc, app_module.UpstreamAPIError):
            return exc
        return app_module.UpstreamAPIError(str(exc))

    async def create_jwt(region: str):
        try:
            account = app_module.get_account_credentials(region)
            token_val, open_id = await app_module.get_access_token(account)
            body = json.dumps({
                "open_id": open_id,
                "open_id_type": "4",
                "login_token": token_val,
                "orign_platform_type": "4",
            })
            proto_bytes = await app_module.json_to_proto(
                body, app_module.FreeFire_pb2.LoginReq()
            )
            payload = app_module.aes_cbc_encrypt(
                app_module.MAIN_KEY, app_module.MAIN_IV, proto_bytes
            )

            async with async_client_factory(timeout=10.0) as client:
                resp = await client.post(
                    protocol.LOGIN_URL,
                    content=payload,
                    headers=protocol.binary_headers(),
                )

            protocol.check_status(resp, "MajorLogin")
            msg = protocol.decode_login(resp.content)
            ttl = min(int(msg.ttl or 25200), 25200)
            app_module.cached_tokens[region] = {
                "token": f"Bearer {msg.token}",
                "region": msg.lock_region or region,
                "server_url": protocol.validate_server(msg.server_url),
                "expires_at": time.time() + ttl,
            }
        except protocol.UpstreamError as exc:
            raise upstream_error(exc) from exc
        except httpx.HTTPError as exc:
            raise app_module.UpstreamAPIError(
                f"MajorLogin request failed: {app_module._short_upstream_error(exc)}"
            ) from exc
        except app_module.UpstreamAPIError:
            raise
        except Exception as exc:
            raise app_module.UpstreamAPIError(
                app_module._short_upstream_error(exc)
            ) from exc

    async def get_account_information(uid, unk, region, endpoint):
        try:
            region = region.upper()
            if region not in app_module.SUPPORTED_REGIONS:
                raise ValueError(f"Unsupported region: {region}")

            payload = await app_module.json_to_proto(
                json.dumps({"a": uid, "b": unk}),
                app_module.main_pb2.GetPlayerPersonalShow(),
            )
            data_enc = app_module.aes_cbc_encrypt(
                app_module.MAIN_KEY, app_module.MAIN_IV, payload
            )
            token, _lock, server = await app_module.get_token_info(region)
            server = protocol.validate_server(server)
            headers = {**protocol.binary_headers(), "Authorization": token}

            async with async_client_factory(timeout=10.0) as client:
                resp = await client.post(
                    server + endpoint,
                    content=data_enc,
                    headers=headers,
                )

            protocol.check_status(resp, "Player lookup")
            decoded = app_module.decode_protobuf(
                resp.content,
                app_module.AccountPersonalShow_pb2.AccountPersonalShowInfo,
            )
            return json.loads(app_module.json_format.MessageToJson(decoded))
        except protocol.UpstreamError as exc:
            raise upstream_error(exc) from exc
        except httpx.HTTPError as exc:
            raise app_module.UpstreamAPIError(
                f"Player info request failed: {app_module._short_upstream_error(exc)}"
            ) from exc
        except app_module.UpstreamAPIError:
            raise
        except Exception as exc:
            raise app_module.UpstreamAPIError(
                f"Player info response could not be decoded: {app_module._short_upstream_error(exc)}"
            ) from exc

    app_module.create_jwt = create_jwt
    app_module.GetAccountInformation = get_account_information
    app_module.OB55_PROTOCOL_MODE = "upstream-v2.2"
    return create_jwt, get_account_information
