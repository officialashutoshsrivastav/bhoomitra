import pytest


def test_workspace_collaboration_flow(client, make_user, admin_headers, gis_analyst):
    ph, pm = make_user(["researcher"])  # owner without workspace.manage
    rh, ruser = make_user(["data_analyst"])
    gh, guser = gis_analyst
    ws = client.post("/api/v1/workspaces", json={"name": "Test workspace", "objective": "Collaborate", "tags": ["test"]}, headers=ph).json()
    assert ws["status"] == "draft" and ws["my_role"] == "owner"
    assert client.get(f"/api/v1/workspaces/{ws['id']}", headers=rh).status_code == 403, "non-members cannot view private workspace"
    assert client.post(f"/api/v1/workspaces/{ws['id']}/members", json={"user_id": ruser["id"], "role": "editor"}, headers=ph).status_code == 201
    r = client.post(f"/api/v1/workspaces/{ws['id']}/members", json={"email": guser["email"], "role": "viewer"}, headers=ph)
    assert r.status_code == 201 and len(r.json()["members"]) == 3
    assert client.post(f"/api/v1/workspaces/{ws['id']}/members", json={"user_id": ruser["id"]}, headers=ph).status_code == 409
    task = client.post(f"/api/v1/workspaces/{ws['id']}/tasks", json={"title": "Do analysis", "assignee_id": guser["id"], "priority": "high"}, headers=rh).json()
    assert task["status"] == "todo"
    assert client.post(f"/api/v1/workspaces/{ws['id']}/tasks", json={"title": "viewer task"}, headers=gh).status_code == 403
    done = client.patch(f"/api/v1/workspaces/{ws['id']}/tasks/{task['id']}", json={"status": "done"}, headers=rh).json()
    assert done["completed_at"]
    assert client.post(f"/api/v1/workspaces/{ws['id']}/resources", json={"resource_type": "moon_base", "resource_id": ws["id"]}, headers=rh).status_code == 422
    c = client.post(f"/api/v1/workspaces/{ws['id']}/comments", json={"body": "Looks good"}, headers=rh).json()
    assert c["author_name"]
    notes = client.get("/api/v1/notifications", headers=gh).json()
    assert notes["unread"] >= 1 and any("Added to workspace" in n["title"] or "Task" in n["title"] for n in notes["items"])
    assert client.post(f"/api/v1/workspaces/{ws['id']}/transition", json={"status": "published"}, headers=ph).status_code == 409
    assert client.post(f"/api/v1/workspaces/{ws['id']}/transition", json={"status": "active"}, headers=ph).json()["status"] == "active"
    assert client.post(f"/api/v1/workspaces/{ws['id']}/transition", json={"status": "review"}, headers=ph).json()["status"] == "review"
    assert client.post(f"/api/v1/workspaces/{ws['id']}/transition", json={"status": "published"}, headers=ph).status_code == 403, "owner needs an approved review to publish"
    q = client.get("/api/v1/admin/approvals", params={"target_type": "workspace"}, headers=admin_headers).json()
    approval = next(a for a in q["items"] if a["target_id"] == ws["id"])
    assert client.post(f"/api/v1/admin/approvals/{approval['id']}/decide", json={"decision": "approve"}, headers=admin_headers).status_code == 200
    assert client.post(f"/api/v1/workspaces/{ws['id']}/transition", json={"status": "published"}, headers=ph).json()["status"] == "published"
    acts = client.get(f"/api/v1/workspaces/{ws['id']}/activity", headers=rh).json()["items"]
    assert {a["action"] for a in acts} >= {"workspace.created", "member.added", "task.created", "comment.added", "workspace.status_changed"}
    assert client.delete(f"/api/v1/workspaces/{ws['id']}/members/{pm['id']}", headers=ph).status_code == 409, "owner cannot be removed"


def test_innovation_challenge_lifecycle(client, make_user, researcher):
    mh, _ = make_user(["project_manager"])
    eh, _ = make_user(["innovation_evaluator"])
    rh, _ = researcher
    ch = client.post("/api/v1/challenges", json={"title": "Test challenge", "summary": "Seeking ideas", "theme": "land records", "closes_at": "2030-01-01T00:00:00Z"}, headers=mh).json()
    assert ch["status"] == "draft" and ch["evaluation_criteria"]
    assert client.get(f"/api/v1/challenges/{ch['id']}").status_code == 404, "drafts are not public"
    assert client.post(f"/api/v1/challenges/{ch['id']}/transition", json={"status": "open"}, headers=mh).status_code == 409, "must publish first"
    assert client.post(f"/api/v1/challenges/{ch['id']}/transition", json={"status": "published"}, headers=mh).json()["status"] == "published"
    assert client.post(f"/api/v1/challenges/{ch['id']}/transition", json={"status": "open"}, headers=mh).json()["is_open"] is True
    assert client.get(f"/api/v1/challenges/{ch['id']}").status_code == 200
    sub = client.post(f"/api/v1/challenges/{ch['id']}/submissions", json={"title": "Idea", "abstract": "Abstract text"}, headers=rh).json()
    assert sub["status"] == "draft"
    a = client.post(f"/api/v1/submissions/{sub['id']}/attachments", files={"file": ("p.txt", b"proposal", "text/plain")}, headers=rh)
    assert a.status_code == 201
    assert client.post(f"/api/v1/submissions/{sub['id']}/evaluate", json={"scores": {"relevance": 8}}, headers=eh).status_code == 409, "cannot evaluate drafts"
    assert client.post(f"/api/v1/submissions/{sub['id']}/submit", headers=rh).json()["status"] == "submitted"
    assert client.get(f"/api/v1/submissions/{sub['id']}", headers=mh).status_code == 200
    bad = client.post(f"/api/v1/submissions/{sub['id']}/evaluate", json={"scores": {"relevance": 11, "feasibility": 7, "impact": 9, "evidence": 6}}, headers=eh)
    assert bad.status_code == 422
    ev = client.post(f"/api/v1/submissions/{sub['id']}/evaluate", json={"scores": {"relevance": 8, "feasibility": 7, "impact": 9, "evidence": 6}, "recommendation": "shortlist"}, headers=eh).json()
    assert ev["status"] == "under_evaluation" and ev["evaluations"][0]["weighted_score"] == 76.5
    assert client.post(f"/api/v1/submissions/{sub['id']}/evaluate", json={"scores": {"relevance": 1, "feasibility": 1, "impact": 1, "evidence": 1}}, headers=rh).status_code == 403, "applicant cannot evaluate own submission"
    client.post(f"/api/v1/challenges/{ch['id']}/transition", json={"status": "evaluation"}, headers=mh)
    assert client.post(f"/api/v1/challenges/{ch['id']}/transition", json={"status": "shortlisted"}, headers=mh).json()["status"] == "shortlisted"
    mine = client.get("/api/v1/submissions/mine", headers=rh).json()["items"]
    assert mine[0]["status"] == "shortlisted" and mine[0]["average_score"] == 76.5
    pilot = client.post(f"/api/v1/submissions/{sub['id']}/pilots", json={"title": "Pilot"}, headers=mh)
    assert pilot.status_code == 201
    assert client.get(f"/api/v1/challenges/{ch['id']}").json()["status"] == "pilot"
    assert client.get("/api/v1/innovation/pilots", headers=mh).json()["items"][0]["status"] == "planned"
