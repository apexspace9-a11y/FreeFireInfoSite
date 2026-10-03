import os

import httpx


DEFAULT_FALLBACK_URL = "https://api2.nftoken.info/get"


def adapt_player_payload(raw: dict, uid: str) -> dict:
    account = raw.get("AccountInfo") or {}
    profile = raw.get("AccountProfileInfo") or {}
    guild = raw.get("GuildInfo") or {}
    social = raw.get("socialInfo") or raw.get("socialinfo") or {}

    basic = {
        "accountId": str(account.get("AccountID") or account.get("AccountId") or uid),
        "accountType": account.get("AccountType", 1),
        "nickname": account.get("AccountName") or account.get("nickname") or "",
        "region": account.get("AccountRegion") or account.get("region") or "",
        "level": account.get("AccountLevel") or account.get("level") or 0,
        "exp": account.get("AccountEXP") or account.get("exp") or 0,
        "bannerId": account.get("AccountBannerId") or account.get("bannerId") or 0,
        "headPic": account.get("AccountAvatarId") or account.get("headPic") or 0,
        "rank": account.get("BrMaxRank") or account.get("rank") or 0,
        "rankingPoints": account.get("BrRankPoint") or account.get("rankingPoints") or 0,
        "liked": account.get("AccountLikes") or account.get("liked") or 0,
        "seasonId": account.get("AccountSeasonId") or account.get("seasonId") or 0,
        "csRank": account.get("CsMaxRank") or account.get("csRank") or 0,
        "csRankingPoints": account.get("CsRankPoint") or account.get("csRankingPoints") or 0,
        "maxRank": account.get("BrMaxRank") or account.get("maxRank") or 0,
        "csMaxRank": account.get("CsMaxRank") or account.get("csMaxRank") or 0,
        "createAt": str(account.get("AccountCreateTime") or account.get("createAt") or ""),
        "lastLoginAt": str(account.get("AccountLastLogin") or account.get("lastLoginAt") or ""),
        "weaponSkinShows": account.get("EquippedWeapon") or account.get("weaponSkinShows") or [],
        "title": account.get("Title") or account.get("title") or 0,
    }

    clan = {
        "clanId": str(guild.get("GuildID") or guild.get("clanId") or ""),
        "clanName": guild.get("GuildName") or guild.get("clanName") or "",
        "clanLevel": guild.get("GuildLevel") or guild.get("clanLevel") or 0,
        "memberNum": guild.get("GuildMember") or guild.get("memberNum") or 0,
        "capacity": guild.get("GuildCapacity") or guild.get("capacity") or 0,
        "captainId": str(guild.get("GuildOwner") or guild.get("captainId") or ""),
    }

    profile_info = {
        "avatarId": basic["headPic"],
        "clothes": profile.get("EquippedOutfit") or profile.get("clothes") or [],
        "equipedSkills": profile.get("EquippedSkills") or profile.get("equipedSkills") or [],
    }

    return {
        "basicInfo": basic,
        "profileInfo": profile_info,
        "clanBasicInfo": clan,
        "captainBasicInfo": raw.get("captainBasicInfo") or {},
        "creditScoreInfo": raw.get("creditScoreInfo") or {},
        "petInfo": raw.get("petInfo") or {},
        "socialInfo": social,
        "_dataSource": "public-fallback",
    }


def install_player_info_fallback(app_module):
    original_get_player_data = app_module.get_player_data
    fallback_url = os.getenv("FF_PLAYER_INFO_FALLBACK_URL", DEFAULT_FALLBACK_URL).strip() or DEFAULT_FALLBACK_URL

    def get_player_data(uid: str, region: str = None):
        try:
            return original_get_player_data(uid, region)
        except app_module.UpstreamAPIError as original_error:
            if "BR_AUTH_ABNORMAL_GAME_CLIENT" not in str(original_error):
                raise

            safe_uid = app_module.validate_uid(uid)
            params = {"uid": safe_uid}
            if region:
                params["region"] = app_module.normalize_region(region)

            try:
                response = httpx.get(fallback_url, params=params, timeout=12.0, follow_redirects=True)
                response.raise_for_status()
                raw = response.json()
                if not isinstance(raw, dict) or raw.get("error"):
                    raise ValueError(str(raw.get("error") or "invalid fallback response"))
                data = adapt_player_payload(raw, safe_uid)
                basic = data.get("basicInfo") or {}
                if not basic.get("nickname"):
                    raise ValueError("fallback response did not contain player nickname")
                detected_region = basic.get("region") or (params.get("region") or "")
                cache_key = (detected_region, safe_uid)
                with app_module.player_data_cache_lock:
                    app_module.player_data_cache[cache_key] = data
                return data, safe_uid, detected_region
            except Exception as fallback_error:
                raise app_module.UpstreamAPIError(
                    f"Free Fire rejected the direct login client; public fallback also failed: {fallback_error}"
                ) from fallback_error

    app_module.get_player_data = get_player_data
    return get_player_data
