from app.core.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS, P, Roles


def test_permission_matrix_is_consistent():
    assert len(ROLE_PERMISSIONS) == 13
    for role, perms in ROLE_PERMISSIONS.items():
        assert perms, f"{role} has no permissions"
        assert set(perms) <= set(ALL_PERMISSIONS), f"{role} references unknown permission"
    assert set(ROLE_PERMISSIONS[Roles.SUPER_ADMIN]) == set(ALL_PERMISSIONS)
    assert P.ADMIN_MANAGE_USERS not in ROLE_PERMISSIONS[Roles.RESEARCHER]
    assert P.SIMULATION_APPROVE in ROLE_PERMISSIONS[Roles.POLICY_MAKER]
    assert P.SIMULATION_APPROVE not in ROLE_PERMISSIONS[Roles.PUBLIC]


def test_public_user_cannot_create_document(client, public_user):
    h, _ = public_user
    r = client.post("/api/v1/documents", json={"title": "Forbidden doc", "document_type": "working_paper"}, headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required"] == ["document.create"]


def test_researcher_can_create_document_but_not_publish(client, researcher):
    h, _ = researcher
    r = client.post("/api/v1/documents", json={"title": "Researcher doc", "document_type": "working_paper"}, headers=h)
    assert r.status_code == 201
    r = client.post(f"/api/v1/documents/{r.json()['id']}/publish", headers=h)
    assert r.status_code == 403


def test_anonymous_is_rejected_on_protected_routes(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.post("/api/v1/ai/ask", json={"question": "hello world?"}).status_code == 401


def test_admin_role_assignment_changes_permissions(client, admin_headers, make_user):
    h, user = make_user(["public_user"])
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert "gis.analyze" not in me["permissions"]
    r = client.put(f"/api/v1/admin/users/{user['id']}/roles", json={"roles": ["gis_analyst"]}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["roles"] == ["gis_analyst"]
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert "gis.analyze" in me["permissions"]


def test_non_admin_cannot_grant_roles(client, researcher, public_user):
    rh, _ = researcher
    _, pub = public_user
    r = client.put(f"/api/v1/admin/users/{pub['id']}/roles", json={"roles": ["super_administrator"]}, headers=rh)
    assert r.status_code == 403


def test_disabled_user_cannot_login(client, admin_headers, make_user):
    h, user = make_user(["researcher"], password="Disable@2026x")
    assert client.post(f"/api/v1/admin/users/{user['id']}/disable", headers=admin_headers).status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Disable@2026x"})
    assert r.status_code in (401, 403)
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
