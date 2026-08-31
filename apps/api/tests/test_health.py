def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["brand"] == "Букер"
    assert body["flags"]["composition_v2"] is True
    assert body["flags"]["workspace_switcher"] is True
