def test_admin_users_and_roles_matrix(client, admin_headers, researcher):
    rh, _ = researcher
    assert client.get("/api/v1/admin/users", headers=rh).status_code == 403
    r = client.get("/api/v1/admin/users", params={"role": "researcher"}, headers=admin_headers)
    assert r.status_code == 200 and all("researcher" in u["roles"] for u in r.json()["items"])
    roles = client.get("/api/v1/admin/roles", headers=admin_headers).json()
    assert len(roles["roles"]) == 13 and len(roles["permissions"]) >= 40


def test_approvals_queue_and_audit(client, admin_headers, researcher, official):
    rh, _ = researcher
    did = client.post("/api/v1/documents", json={"title": "Approval queue doc", "document_type": "working_paper"}, headers=rh).json()["id"]
    client.post(f"/api/v1/documents/{did}/versions", files={"file": ("q.txt", b"Queue content " * 30, "text/plain")}, headers=rh)
    client.post(f"/api/v1/documents/{did}/submit", headers=rh)
    q = client.get("/api/v1/admin/approvals", headers=admin_headers).json()
    item = next(a for a in q["items"] if a["target_id"] == did)
    assert item["status"] == "pending" and item["target_type"] == "document"
    r = client.post(f"/api/v1/admin/approvals/{item['id']}/decide", json={"decision": "approve", "note": "via queue"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert client.get(f"/api/v1/documents/{did}", headers=rh).json()["status"] == "approved"
    audit = client.get("/api/v1/audit", params={"resource_id": did}, headers=admin_headers).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"document.create", "document.upload_version", "document.submit_review", "document.review.approved"} <= actions
    assert client.get("/api/v1/audit", headers=rh).status_code == 403


def test_settings_integrations_jobs(client, admin_headers):
    r = client.put("/api/v1/admin/settings", json={"key": "platform.banner", "value": "Demo mode", "description": "Banner text"}, headers=admin_headers)
    assert r.status_code == 200
    s = client.get("/api/v1/admin/settings", headers=admin_headers).json()
    assert any(i["key"] == "platform.banner" for i in s["items"]) and s["runtime"]["task_execution_mode"] == "inline"
    ints = client.get("/api/v1/integrations", headers=admin_headers).json()["items"]
    assert {i["connector"] for i in ints} >= {"geoboundaries", "opensearch", "object_storage", "openai", "stac_satellite"}
    chk = client.post("/api/v1/integrations/object_storage/check", headers=admin_headers).json()
    assert chk["status"] == "ok"
    jobs = client.get("/api/v1/admin/jobs", headers=admin_headers).json()
    assert jobs["total"] >= 1 and jobs["workers"]["mode"] == "inline"
    assert client.get("/api/v1/admin/overview", headers=admin_headers).json()["users"]["total"] >= 1


def test_dashboards(client, admin_headers, researcher):
    pub = client.get("/api/v1/dashboards/public-overview").json()
    assert {s["key"] for s in pub["stats"]} >= {"documents", "datasets", "policies", "gis_layers"}
    assert all(isinstance(s["value"], int) for s in pub["stats"])
    rh, _ = researcher
    me = client.get("/api/v1/dashboards/me", headers=rh).json()
    assert "my_activity" in me["widgets"] and "research" in me["widgets"] and "admin" not in me["widgets"]
    assert client.get("/api/v1/dashboards/national", headers=rh).status_code == 403
    assert "states" in client.get("/api/v1/dashboards/national", headers=admin_headers).json()


def test_reports_csv_xlsx_pdf(client, admin_headers):
    for fmt, magic in (("csv", b"\xef\xbb\xbfReport"), ("xlsx", b"PK"), ("pdf", b"%PDF")):
        r = client.post("/api/v1/reports", json={"title": f"Summary {fmt}", "report_type": "repository_summary", "format": fmt, "background": False}, headers=admin_headers)
        assert r.status_code == 202, r.text
        rep = r.json()
        assert rep["status"] == "ready" and rep["file_size"] > 0
        d = client.get(f"/api/v1/reports/{rep['id']}/download", headers=admin_headers)
        assert d.status_code == 200 and d.content.startswith(magic), fmt
    assert client.get("/api/v1/reports", headers=admin_headers).json()["total"] >= 3
    r = client.post("/api/v1/reports", json={"title": "bad", "report_type": "dataset_export", "format": "csv", "parameters": {"dataset_id": "00000000-0000-0000-0000-000000000000"}, "background": False}, headers=admin_headers)
    assert r.status_code == 404
