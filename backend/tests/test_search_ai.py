def test_hybrid_search_finds_body_terms(client, published_document):
    doc = published_document["doc"]
    r = client.get("/api/v1/search", params={"q": "drones boundary disputes"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    hit = next(h for h in body["items"] if h["id"] == doc["id"])
    assert "keyword" in hit["matched_by"] and "semantic" in hit["matched_by"]
    assert body["relevance"]["fusion"] == "rrf" and body["relevance"]["vector_backend"] == "pgvector"


def test_search_filters_and_types(client, published_document):
    r = client.get("/api/v1/search", params={"q": "land records", "types": "dataset,policy"})
    assert r.status_code == 200 and all(h["entity_type"] in ("dataset", "policy") for h in r.json()["items"])
    r = client.get("/api/v1/search", params={"q": "land records", "document_type": "research_paper"})
    assert all(h["metadata"].get("document_type") == "research_paper" for h in r.json()["items"] if h["entity_type"] == "document")


def test_autocomplete_facets_saved(client, researcher, published_document):
    rh, _ = researcher
    r = client.get("/api/v1/search/autocomplete", params={"q": "Test Land"})
    assert r.status_code == 200 and any("Test Land Records" in s["label"] for s in r.json()["suggestions"])
    assert "document_type" in client.get("/api/v1/search/facets").json()
    r = client.post("/api/v1/search/saved", json={"name": "my search", "query": "drones", "filters": {"topic": "land records"}}, headers=rh)
    assert r.status_code == 201
    sid = r.json()["id"]
    assert any(s["id"] == sid for s in client.get("/api/v1/search/saved", headers=rh).json()["items"])
    assert client.delete(f"/api/v1/search/saved/{sid}", headers=rh).status_code == 200
    assert client.get("/api/v1/search/recent", headers=rh).status_code == 200


def test_ai_ask_returns_citations_and_trace(client, researcher, published_document):
    rh, _ = researcher
    r = client.post("/api/v1/ai/ask", json={"question": "By how much did drone resurvey reduce boundary disputes?"}, headers=rh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence_sufficient"] is True
    assert body["citations"] and all(c["document_id"] for c in body["citations"])
    assert "22 percent" in body["answer"]
    assert "[1]" in body["answer"] or "[2]" in body["answer"]
    assert body["provider"] == "local-extractive"
    rec = body["recommendation_id"]
    ex = client.get(f"/api/v1/evidence/{rec}", headers=rh).json()
    assert ex["evidence"] and ex["evidence"][0]["type"] == "document_chunk"
    tr = client.get(f"/api/v1/evidence/{rec}/trace", headers=rh).json()
    types = {n["type"] for n in tr["nodes"]}
    assert {"recommendation", "evidence", "document_chunk", "document_version", "document"} <= types
    assert tr["edges"]
    conv = client.get(f"/api/v1/ai/conversations/{body['conversation_id']}", headers=rh).json()
    assert len(conv["messages"]) == 2 and conv["messages"][1]["citations"]


def test_ai_refuses_without_evidence(client, researcher, published_document):
    rh, _ = researcher
    r = client.post("/api/v1/ai/ask", json={"question": "What is the orbital period of Neptune?"}, headers=rh)
    assert r.status_code == 200
    body = r.json()
    assert body["evidence_sufficient"] is False and body["confidence"] == 0.0
    assert "could not find sufficient evidence" in body["answer"].lower()
    assert not body["citations"] or all(not c["cited_in_answer"] for c in body["citations"])


def test_ai_status(client, researcher):
    rh, _ = researcher
    st = client.get("/api/v1/ai/status", headers=rh).json()
    assert st["embeddings"]["dim"] == 1536 and st["retrieval"]["vector_store"] == "pgvector"
