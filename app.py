"""
Free Fire Info Site & API — Official Media Edition
Developer: refatbd (https://github.com/refatbd)
"""

import asyncio
import time
import httpx
import json
from collections import defaultdict
from flask import Flask, request, jsonify, render_template, Response, url_for
from flask_cors import CORS
from cachetools import TTLCache
from typing import Tuple
from proto import FreeFire_pb2, main_pb2, AccountPersonalShow_pb2
from google.protobuf import json_format, message
from google.protobuf.message import Message
from Crypto.Cipher import AES
import base64
import threading
import os

from official_media import render_player_avatar, render_player_banner, validate_uid

# === Settings ===
MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')
MAIN_IV = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')
RELEASEVERSION = os.getenv("FF_RELEASE_VERSION", "OB55").strip().upper()
USERAGENT = "Dalvik/2.1.0 (Linux; U; Android 13; CPH2095 Build/RKQ1.211119.001)"
GUEST_TOKEN_URL = os.getenv(
    "FF_GUEST_TOKEN_URL",
    "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant",
).strip()
MAJOR_LOGIN_URL = os.getenv(
    "FF_MAJOR_LOGIN_URL",
    "https://loginbp.ggpolarbear.com/MajorLogin",
).strip()
SUPPORTED_REGIONS = {"IND", "BR", "US", "SAC", "NA", "SG", "RU", "ID", "TW", "VN", "TH", "ME", "PK", "CIS", "BD", "EUROPE"}
REGION_ALIASES = {"EU": "EUROPE"}

# === Flask App Setup ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))
CORS(app)
player_data_cache = TTLCache(maxsize=256, ttl=300)
player_data_cache_lock = threading.RLock()
cached_tokens = defaultdict(dict)

class UpstreamAPIError(RuntimeError):
    """Raised when the current Free Fire upstream login/player service is unavailable."""


def _short_upstream_error(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:240] if text else exc.__class__.__name__


# === Helper Functions ===
def pad(text: bytes) -> bytes:
    padding_length = AES.block_size - (len(text) % AES.block_size)
    return text + bytes([padding_length] * padding_length)

def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    aes = AES.new(key, AES.MODE_CBC, iv)
    return aes.encrypt(pad(plaintext))

def decode_protobuf(encoded_data: bytes, message_type: message.Message) -> message.Message:
    instance = message_type()
    instance.ParseFromString(encoded_data)
    return instance

async def json_to_proto(json_data: str, proto_message: Message) -> bytes:
    json_format.ParseDict(json.loads(json_data), proto_message)
    return proto_message.SerializeToString()

def get_account_credentials(region: str) -> str:
    r = region.upper()
    if r == "IND":
        return "uid=3692279677&password=473AFFEF67F708CBB0962A958BB2809DA0843EA41BDB70D738FD9527EA04B27B"
    elif r in {"BR", "US", "SAC", "NA", "EUROPE"}:
        return "uid=3692292847&password=FC22F6812C850FF7D8DB8C5474A106B6FE22CB10C0A6673837216A32675E5649"
    elif r == "VN":
        return "uid=3686689562&password=AD9C4A2B51A749481913F72A36F68A9F231520E9AC29B244DB47A64FD7353A12"
    elif r == "ID":
        return "uid=3692307512&password=4AA06E1DB3F998ABDBDA74578D26B0C84700EC5C079751E7C8F1626048DDBCAE"
    elif r == "TH":
        return "uid=3692333198&password=0ED64C5A89E09B8BE538829B0304FE5F5F7EA3BBE645A341C73ECA49143D2211"
    elif r == "TW":
        return "uid=3692312456&password=1A062FD700DA8F826AF84A37EE2B62121B79516AF71666949C72FFF42D1C554A"
    else:
        # SG Primary Global Gateway for BD, ME, PK, CIS, SG, etc.
        return "uid=3692265171&password=A2A5E3C252A35B2BB30698BD1469A759417A68A069CF6980ED959EB01D352E28"

# === Token Generation ===
async def get_access_token(account: str):
    payload = account + "&response_type=token&client_type=2&client_secret=2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3&client_id=100067"
    headers = {
        'User-Agent': USERAGENT,
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/x-www-form-urlencoded",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(GUEST_TOKEN_URL, data=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamAPIError(f"Guest token request failed: {_short_upstream_error(exc)}") from exc

    token_val = data.get("access_token")
    open_id = data.get("open_id")
    if not token_val or not open_id:
        raise UpstreamAPIError("Guest token response did not include access_token/open_id.")
    return token_val, open_id

async def create_jwt(region: str):
    try:
        account = get_account_credentials(region)
        token_val, open_id = await get_access_token(account)
        body = json.dumps({"open_id": open_id, "open_id_type": "4", "login_token": token_val, "orign_platform_type": "4"})
        proto_bytes = await json_to_proto(body, FreeFire_pb2.LoginReq())
        payload = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, proto_bytes)
        headers = {
            'User-Agent': USERAGENT,
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/octet-stream",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': RELEASEVERSION,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(MAJOR_LOGIN_URL, data=payload, headers=headers)
            if resp.status_code < 200 or resp.status_code >= 300:
                raise UpstreamAPIError(f"MajorLogin returned HTTP {resp.status_code}.")
            if not resp.content:
                raise UpstreamAPIError("MajorLogin returned an empty response.")

        try:
            decoded = decode_protobuf(resp.content, FreeFire_pb2.LoginRes)
            msg = json.loads(json_format.MessageToJson(decoded))
        except Exception as exc:
            raise UpstreamAPIError(
                f"MajorLogin response could not be decoded for {RELEASEVERSION}: {_short_upstream_error(exc)}"
            ) from exc

        token = msg.get('token')
        server_url = msg.get('serverUrl')
        if not token or not server_url:
            raise UpstreamAPIError("MajorLogin response did not contain token/serverUrl.")

        cached_tokens[region] = {
            'token': f"Bearer {token}",
            'region': msg.get('lockRegion', region),
            'server_url': server_url,
            'expires_at': time.time() + 25200,
        }
    except Exception as exc:
        print(f"Error fetching token for region {region}: {_short_upstream_error(exc)}")
        if isinstance(exc, UpstreamAPIError):
            raise
        raise UpstreamAPIError(_short_upstream_error(exc)) from exc

async def initialize_tokens():
    tasks = [create_jwt(r) for r in SUPPORTED_REGIONS]
    await asyncio.gather(*tasks, return_exceptions=True)

async def refresh_tokens_periodically():
    while True:
        await asyncio.sleep(25200)
        await initialize_tokens()

async def get_token_info(region: str) -> Tuple[str,str,str]:
    info = cached_tokens.get(region)
    if info and time.time() < info['expires_at']:
        return info['token'], info['region'], info['server_url']
    await create_jwt(region)
    info = cached_tokens.get(region)
    if not info:
        raise RuntimeError(f"Failed to acquire token for region {region}")
    return info['token'], info['region'], info['server_url']

async def GetAccountInformation(uid, unk, region, endpoint):
    region = region.upper()
    if region not in SUPPORTED_REGIONS:
        raise ValueError(f"Unsupported region: {region}")
    payload = await json_to_proto(json.dumps({'a': uid, 'b': unk}), main_pb2.GetPlayerPersonalShow())
    data_enc = aes_cbc_encrypt(MAIN_KEY, MAIN_IV, payload)
    token, lock, server = await get_token_info(region)
    if not server.startswith("http://") and not server.startswith("https://"):
        server = "https://" + server
    headers = {'User-Agent': USERAGENT, 'Connection': "Keep-Alive", 'Accept-Encoding': "gzip",
               'Content-Type': "application/octet-stream", 'Expect': "100-continue",
               'Authorization': token, 'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1",
               'ReleaseVersion': RELEASEVERSION}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(server + endpoint, data=data_enc, headers=headers)
            resp.raise_for_status()
            if not resp.content:
                raise UpstreamAPIError("Player info endpoint returned an empty response.")
        decoded = decode_protobuf(resp.content, AccountPersonalShow_pb2.AccountPersonalShowInfo)
        return json.loads(json_format.MessageToJson(decoded))
    except UpstreamAPIError:
        raise
    except httpx.HTTPStatusError as exc:
        raise UpstreamAPIError(f"Player info endpoint returned HTTP {exc.response.status_code}.") from exc
    except httpx.HTTPError as exc:
        raise UpstreamAPIError(f"Player info request failed: {_short_upstream_error(exc)}") from exc
    except Exception as exc:
        raise UpstreamAPIError(f"Player info response could not be decoded: {_short_upstream_error(exc)}") from exc



GATEWAY_REGIONS = ["BD", "SG", "IND", "BR", "VN", "ID", "TH", "TW"]

def normalize_region(region: str) -> str:
    value = str(region or "").strip().upper()
    value = REGION_ALIASES.get(value, value)
    if value not in SUPPORTED_REGIONS:
        raise ValueError(f"Unsupported region: {value or 'missing'}")
    return value


def get_player_data(uid: str, region: str = None):
    safe_uid = validate_uid(uid)
    
    if region:
        safe_region = normalize_region(region)
        cache_key = (safe_region, safe_uid)
        with player_data_cache_lock:
            cached_player = player_data_cache.get(cache_key)
        if cached_player is not None:
            return cached_player, safe_uid, safe_region

        player_data = asyncio.run(
            GetAccountInformation(safe_uid, "7", safe_region, "/GetPlayerPersonalShow")
        )
        basic = player_data.get("basicInfo") or {}
        if not basic.get("nickname"):
            raise ValueError(f"No player found for UID '{safe_uid}' in region {safe_region}.")
        with player_data_cache_lock:
            player_data_cache[cache_key] = player_data
        return player_data, safe_uid, safe_region
    else:
        # Check cache for any cached region entry matching safe_uid
        with player_data_cache_lock:
            for (cached_reg, cached_u), data in player_data_cache.items():
                if cached_u == safe_uid:
                    return data, safe_uid, cached_reg

        # Auto-detect region across gateway clusters concurrently
        async def _find_auto():
            async def _try_reg(reg):
                try:
                    res = await GetAccountInformation(safe_uid, "7", reg, "/GetPlayerPersonalShow")
                    basic = res.get("basicInfo") or {}
                    if basic and basic.get("nickname"):
                        det_reg = basic.get("region") or reg
                        return (res, det_reg), None
                    return None, None
                except Exception as exc:
                    return None, f"{reg}: {_short_upstream_error(exc)}"

            tasks = [_try_reg(r) for r in GATEWAY_REGIONS]
            results = await asyncio.gather(*tasks)
            errors = []
            for found, error in results:
                if found is not None:
                    return found, []
                if error:
                    errors.append(error)
            return None, errors

        result, upstream_errors = asyncio.run(_find_auto())
        if not result:
            if upstream_errors:
                raise UpstreamAPIError(
                    "Free Fire upstream login/player service is unavailable. "
                    f"First error: {upstream_errors[0]}"
                )
            raise ValueError(f"Player account not found for UID '{safe_uid}'.")

        player_data, safe_region = result
        cache_key = (safe_region, safe_uid)
        with player_data_cache_lock:
            player_data_cache[cache_key] = player_data
        return player_data, safe_uid, safe_region


def media_response(rendered):
    response = Response(rendered.data, mimetype="image/webp")
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Free-Fire-Media-Source"] = rendered.source
    response.headers["X-Free-Fire-Official-Banner"] = "1" if rendered.official_banner else "0"
    response.headers["X-Free-Fire-Official-Avatar"] = "1" if rendered.official_avatar else "0"
    return response

# === Flask Routes ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/player-info')
def get_account_info():
    region = request.args.get('region')
    uid = request.args.get('uid')

    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    try:
        return_data, safe_uid, safe_region = get_player_data(uid, region)
        basic = return_data.get("basicInfo") or {}
        version = f"v7-{basic.get('bannerId', '0')}-{basic.get('headPic', '0')}-{int(time.time())}"
        return_data["mediaInfo"] = {
            "bannerUrl": url_for(
                "get_player_banner", uid=safe_uid, region=safe_region, v=version
            ),
            "avatarUrl": url_for(
                "get_player_avatar", uid=safe_uid, region=safe_region, v=version
            ),
            "policy": "official-free-fire-cdn-only-with-local-fallback",
        }
        return jsonify(return_data), 200
    except UpstreamAPIError as e:
        return jsonify({"error": str(e)}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server Error: {str(e)}"}), 500


@app.route('/api/banner/banner_<uid>.webp')
def get_player_banner(uid):
    region = request.args.get('region')
    try:
        player_data, _, _ = get_player_data(uid, region)
        return media_response(render_player_banner(player_data))
    except UpstreamAPIError as e:
        return jsonify({"error": str(e)}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Banner generation failed: {str(e)}"}), 502


@app.route('/api/avatar/avatar_<uid>.webp')
def get_player_avatar(uid):
    region = request.args.get('region')
    try:
        player_data, _, _ = get_player_data(uid, region)
        return media_response(render_player_avatar(player_data))
    except UpstreamAPIError as e:
        return jsonify({"error": str(e)}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Avatar generation failed: {str(e)}"}), 502


@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "releaseVersion": RELEASEVERSION,
        "majorLoginHost": MAJOR_LOGIN_URL.split("/", 3)[2] if "://" in MAJOR_LOGIN_URL else MAJOR_LOGIN_URL,
    }), 200

@app.route('/refresh', methods=['GET','POST'])
def refresh_tokens_endpoint():
    try:
        asyncio.run(initialize_tokens())
        return jsonify({'message':'Tokens refreshed for all regions.'}),200
    except Exception as e:
        return jsonify({'error': f'Refresh failed: {e}'}),500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)


