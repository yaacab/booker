def test_yandex_and_vk_oauth_are_fail_closed(client):
    for path in (
        "/auth/yandex/start",
        "/auth/yandex/callback",
        "/auth/vk/start",
        "/auth/vk/callback",
    ):
        res = client.get(path)
        assert res.status_code == 503, path
        assert "не настроен" in res.json()["detail"].lower() or "выключен" in res.json()["detail"].lower()
