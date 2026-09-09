import hashlib


def test_upload_processes_and_chunks(client, researcher, published_document):
    rh, _ = researcher
    doc, version = published_document["doc"], published_document["version"]
    r = client.get(f"/api/v1/documents/{doc['id']}/versions/{version['id']}/status", headers=rh)
    assert r.status_code == 200
    st = r.json()
    assert st["processing_status"] == "READY" and st["chunks"] >= 1 and st["job"]["status"] == "completed"
    r = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=rh)
    assert r.json()["total"] >= 1 and "cadastral" in " ".join(c["content"] for c in r.json()["items"])


def test_duplicate_file_rejected(client, researcher, published_document):
    rh, _ = researcher
    doc = published_document["doc"]
    r = client.post("/api/v1/documents", json={"title": "Dup target", "document_type": "working_paper"}, headers=rh)
    did = r.json()["id"]
    payload = b"Same bytes uploaded twice. " * 40
    assert client.post(f"/api/v1/documents/{did}/versions", files={"file": ("a.txt", payload, "text/plain")}, headers=rh).status_code == 201
    r = client.post(f"/api/v1/documents/{did}/versions", files={"file": ("b.txt", payload, "text/plain")}, headers=rh)
    assert r.status_code == 409


def test_malware_and_bad_type_rejected(client, researcher):
    rh, _ = researcher
    did = client.post("/api/v1/documents", json={"title": "Bad uploads", "document_type": "working_paper"}, headers=rh).json()["id"]
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    r = client.post(f"/api/v1/documents/{did}/versions", files={"file": ("virus.txt", eicar, "text/plain")}, headers=rh)
    assert r.status_code in (400, 422), r.text
    r = client.post(f"/api/v1/documents/{did}/versions", files={"file": ("app.exe", b"MZ\x90\x00binary", "application/octet-stream")}, headers=rh)
    assert r.status_code in (400, 415, 422)


def test_workflow_and_visibility(client, researcher, official, public_user):
    rh, _ = researcher
    oh, _ = official
    ph, _ = public_user
    did = client.post("/api/v1/documents", json={"title": "Workflow doc", "document_type": "policy_brief", "visibility": "public"}, headers=rh).json()["id"]
    assert client.post(f"/api/v1/documents/{did}/submit", headers=rh).status_code == 422, "cannot submit without a file"
    client.post(f"/api/v1/documents/{did}/versions", files={"file": ("w.txt", b"Workflow content about tenure security. " * 20, "text/plain")}, headers=rh)
    assert client.get(f"/api/v1/documents/{did}").status_code == 404, "draft not visible anonymously"
    assert client.get(f"/api/v1/documents/{did}", headers=ph).status_code == 404, "draft not visible to other users"
    assert client.post(f"/api/v1/documents/{did}/submit", headers=rh).json()["status"] == "in_review"
    assert client.post(f"/api/v1/documents/{did}/review", json={"decision": "request_changes", "comments": "fix"}, headers=oh).json()["status"] == "draft"
    client.post(f"/api/v1/documents/{did}/submit", headers=rh)
    assert client.post(f"/api/v1/documents/{did}/review", json={"decision": "approve"}, headers=oh).json()["status"] == "approved"
    assert client.post(f"/api/v1/documents/{did}/publish", headers=oh).json()["status"] == "published"
    detail = client.get(f"/api/v1/documents/{did}").json()
    assert detail["status"] == "published" and len(detail["reviews"]) == 2
    assert client.post(f"/api/v1/documents/{did}/archive", headers=oh).json()["status"] == "archived"


def test_download_has_checksum(client, published_document):
    doc = published_document["doc"]
    r = client.get(f"/api/v1/documents/{doc['id']}/download")
    assert r.status_code == 200
    assert r.headers["x-checksum-sha256"] == hashlib.sha256(r.content).hexdigest()
    assert "attachment" in r.headers["content-disposition"]


def test_relations_and_listing_filters(client, researcher, published_document):
    rh, _ = researcher
    doc = published_document["doc"]
    other = client.post("/api/v1/documents", json={"title": "Related working paper", "document_type": "working_paper", "topic": "land records"}, headers=rh).json()
    r = client.post(f"/api/v1/documents/{doc['id']}/relations", json={"related_document_id": other["id"], "relation_type": "related"}, headers=rh)
    assert r.status_code == 201
    assert client.post(f"/api/v1/documents/{doc['id']}/relations", json={"related_document_id": doc["id"]}, headers=rh).status_code == 422
    r = client.get("/api/v1/documents", params={"document_type": "government_report", "year": 2023, "topic": "land records"})
    assert r.status_code == 200 and any(d["id"] == doc["id"] for d in r.json()["items"])
    r = client.get("/api/v1/documents", params={"mine": True}, headers=rh)
    assert all(d["created_by"] == other["created_by"] for d in r.json()["items"])
