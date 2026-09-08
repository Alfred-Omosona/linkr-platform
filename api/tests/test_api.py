"""API contract tests. DEVOPS: this is the suite to gate the pipeline on."""


def test_health_does_not_need_a_database(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # These are what tells us WHICH build is running in an environment.
    assert "version" in body and "git_sha" in body and "env" in body


def test_ready_reports_the_database(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_create_link_generates_a_code(client):
    r = client.post("/api/links", json={"url": "https://example.com/a/long/path"})
    assert r.status_code == 201
    body = r.json()
    assert body["target_url"].startswith("https://example.com")
    assert len(body["code"]) == 7
    assert body["short_url"].endswith(body["code"])
    assert body["hits"] == 0


def test_create_link_with_vanity_code(client):
    r = client.post("/api/links", json={"url": "https://example.com", "code": "docs-v2"})
    assert r.status_code == 201
    assert r.json()["code"] == "docs-v2"


def test_duplicate_vanity_code_is_rejected(client):
    payload = {"url": "https://example.com", "code": "taken"}
    assert client.post("/api/links", json=payload).status_code == 201
    r = client.post("/api/links", json=payload)
    assert r.status_code == 409


def test_reserved_code_is_rejected(client):
    r = client.post("/api/links", json={"url": "https://example.com", "code": "health"})
    assert r.status_code == 400


def test_invalid_url_is_rejected(client):
    r = client.post("/api/links", json={"url": "not-a-url"})
    assert r.status_code == 422


def test_follow_redirects_and_counts_the_hit(client):
    code = client.post("/api/links", json={"url": "https://example.com/dest"}).json()["code"]

    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://example.com/dest"

    client.get(f"/{code}", follow_redirects=False)

    detail = client.get(f"/api/links/{code}").json()
    assert detail["hits"] == 2
    assert detail["last_hit_at"] is not None


def test_unknown_code_is_404(client):
    assert client.get("/nope123", follow_redirects=False).status_code == 404
    assert client.get("/api/links/nope123").status_code == 404


def test_list_returns_newest_first(client):
    for i in range(3):
        client.post("/api/links", json={"url": f"https://example.com/{i}", "code": f"c{i}"})

    rows = client.get("/api/links?limit=2").json()
    assert [r["code"] for r in rows] == ["c2", "c1"]


def test_delete_removes_the_link(client):
    code = client.post("/api/links", json={"url": "https://example.com"}).json()["code"]
    assert client.delete(f"/api/links/{code}").status_code == 204
    assert client.get(f"/api/links/{code}").status_code == 404
    assert client.delete(f"/api/links/{code}").status_code == 404


def test_stats_totals(client):
    code = client.post("/api/links", json={"url": "https://example.com"}).json()["code"]
    client.post("/api/links", json={"url": "https://example.org"})
    client.get(f"/{code}", follow_redirects=False)

    body = client.get("/api/stats").json()
    assert body == {"total_links": 2, "total_hits": 1}
