from player_info_fallback import adapt_player_payload


def test_adapts_public_api_schema_to_existing_site_schema():
    raw = {
        "AccountInfo": {
            "AccountID": "4422076728",
            "AccountName": "Test Player",
            "AccountRegion": "BD",
            "AccountLevel": 71,
            "AccountEXP": 123456,
            "AccountBannerId": 901000116,
            "AccountAvatarId": 902000094,
            "AccountLikes": 999,
            "AccountSeasonId": 51,
            "BrMaxRank": 220,
            "BrRankPoint": 3100,
            "CsMaxRank": 212,
            "CsRankPoint": 2500,
            "AccountCreateTime": 1592000000,
            "AccountLastLogin": 1706295767,
            "EquippedWeapon": [907000001],
            "Title": 904000023,
        },
        "AccountProfileInfo": {"EquippedOutfit": [211000050, 211000051]},
        "GuildInfo": {
            "GuildID": "3001234567",
            "GuildName": "TEST GUILD",
            "GuildLevel": 5,
            "GuildMember": 42,
            "GuildCapacity": 50,
            "GuildOwner": "987654321",
        },
        "captainBasicInfo": {"nickname": "Cap"},
        "creditScoreInfo": {"creditScore": 100},
        "petInfo": {"id": 1300000071},
        "socialinfo": {"signature": "hello"},
    }

    data = adapt_player_payload(raw, "4422076728")
    assert data["basicInfo"]["accountId"] == "4422076728"
    assert data["basicInfo"]["nickname"] == "Test Player"
    assert data["basicInfo"]["region"] == "BD"
    assert data["basicInfo"]["bannerId"] == 901000116
    assert data["basicInfo"]["headPic"] == 902000094
    assert data["clanBasicInfo"]["clanName"] == "TEST GUILD"
    assert data["profileInfo"]["clothes"] == [211000050, 211000051]
    assert data["socialInfo"]["signature"] == "hello"
