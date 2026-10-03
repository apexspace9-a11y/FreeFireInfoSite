import time

import httpx


ABNORMAL_CODE = "BR_AUTH_ABNORMAL_GAME_CLIENT"


def install_direct_guard(app_module, async_client_factory=httpx.AsyncClient):
    """Install a direct-Garena-only MajorLogin guard.

    This keeps the project's existing request payload and headers unchanged.
    It only changes retry behavior: an explicit abnormal-client rejection is
    treated as terminal, while transport errors may still try Garena's other
    configured MajorLogin gateways.
    """

    async def guarded_create_jwt(region: str):
        try:
            account = app_module.get_account_credentials(region)
            token_val, open_id = await app_module.get_access_token(account)
            guest_uid = account.split("&", 1)[0].split("=", 1)[1]
            payload = app_module.build_ob55_major_login_payload(open_id, token_val, guest_uid)

            headers = {
                "User-Agent": f"UnityPlayer/{app_module.UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
                "Accept": "*/*",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "deflate, gzip",
                "X-Ga-Sv": app_module.GA_SERVER_VERSION,
                "Authorization": "Bearer",
                "X-Ga": "v1 1",
                "ReleaseVersion": app_module.RELEASEVERSION,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Unity-Version": app_module.UNITY_VERSION,
            }

            login_urls = []
            for candidate in [app_module.MAJOR_LOGIN_URL, *app_module.MAJOR_LOGIN_FALLBACK_URLS]:
                if candidate and candidate not in login_urls:
                    login_urls.append(candidate)

            failures = []
            msg = None
            async with async_client_factory(timeout=15.0, follow_redirects=True) as client:
                for login_url in login_urls:
                    try:
                        resp = await client.post(login_url, data=payload, headers=headers)
                    except httpx.HTTPError as exc:
                        failures.append(f"{login_url}: {app_module._short_upstream_error(exc)}")
                        continue

                    if resp.status_code < 200 or resp.status_code >= 300:
                        body_preview = resp.text.strip().replace("\n", " ")[:180] if resp.content else ""
                        detail = f"HTTP {resp.status_code}"
                        if body_preview:
                            detail += f" ({body_preview})"

                        if ABNORMAL_CODE in body_preview:
                            raise app_module.UpstreamAPIError(
                                f"Garena rejected the direct Free Fire client ({ABNORMAL_CODE}). "
                                f"ReleaseVersion={app_module.RELEASEVERSION}, "
                                f"clientVersion={app_module.CLIENT_VERSION}. "
                                "Direct Garena mode is enabled; no third-party fallback is used."
                            )

                        failures.append(f"{login_url}: {detail}")
                        continue

                    try:
                        msg = app_module.decode_major_login_wire(resp.content)
                        break
                    except Exception as exc:
                        failures.append(
                            f"{login_url}: decode failed ({app_module._short_upstream_error(exc)})"
                        )

            if msg is None:
                detail = "; ".join(failures[:3]) or "no MajorLogin gateway succeeded"
                raise app_module.UpstreamAPIError(f"MajorLogin failed for {region}: {detail}")

            ttl = int(msg.get("ttl") or 25200)
            if ttl < 300 or ttl > 86400:
                ttl = 25200

            app_module.cached_tokens[region] = {
                "token": f"Bearer {msg['token']}",
                "region": msg.get("lockRegion") or region,
                "server_url": msg["serverUrl"],
                "expires_at": time.time() + ttl,
            }
        except Exception as exc:
            print(
                f"Error fetching token for region {region}: "
                f"{app_module._short_upstream_error(exc)}"
            )
            if isinstance(exc, app_module.UpstreamAPIError):
                raise
            raise app_module.UpstreamAPIError(app_module._short_upstream_error(exc)) from exc

    app_module.create_jwt = guarded_create_jwt
    return guarded_create_jwt
