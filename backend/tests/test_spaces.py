"""Espacios, roles, invitaciones, aislamiento y administración."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.helpers import PASSWORD, Person, invite, join, login, setup_admin, totp_code


@pytest.fixture
def world(client: TestClient, engine: Engine, new_client):  # type: ignore[no-untyped-def]
    """Javier (admin, dueño de «Pareja») y Lucía (dueña de «Familia», colaboradora en «Pareja»)."""
    javier = setup_admin(client, engine)
    lucia = join(new_client(), engine, invite(javier, javier.spaces["Pareja"]), "lucia")
    familia = lucia.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    lucia.spaces["Familia"] = familia
    return javier, lucia


def test_invitation_flow(world, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    javier, _lucia = world
    members = javier.get(f"/api/v1/spaces/{javier.spaces['Pareja']}/members").json()
    assert {m["username"]: m["role"] for m in members} == {"javier": "owner", "lucia": "collaborator"}

    token = invite(javier, javier.spaces["Pareja"], "viewer")
    preview = new_client().get(f"/api/v1/invitations/by-token/{token}").json()
    assert (
        preview["space_name"] == "Pareja"
        and preview["role"] == "viewer"
        and preview["invited_by"] == "Javier"
    )
    pending = javier.get(f"/api/v1/spaces/{javier.spaces['Pareja']}/invitations").json()
    assert (len(pending) == 1 and "url" not in pending[0]) or pending[0]["url"] is None

    abuela = join(new_client(), engine, token, "abuela")
    assert abuela.spaces == {"Pareja": javier.spaces["Pareja"]}
    # Un solo uso
    reuse = new_client().post(
        f"/api/v1/invitations/by-token/{token}/accept",
        json={"username": "otra", "display_name": "Otra", "password": PASSWORD},
    )
    assert reuse.status_code == 404 and reuse.json()["code"] == "invalid_link"


def test_invitation_expiry_and_revocation(world, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    javier, _ = world
    space = javier.spaces["Pareja"]
    expired = invite(javier, space)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE invitations SET expires_at = now() - interval '1 minute' WHERE used_at IS NULL")
        )
    assert new_client().get(f"/api/v1/invitations/by-token/{expired}").status_code == 404
    revoked = invite(javier, space)
    inv_id = javier.get(f"/api/v1/spaces/{space}/invitations").json()[0]["id"]
    assert javier.delete(f"/api/v1/invitations/{inv_id}").status_code == 204
    assert new_client().get(f"/api/v1/invitations/by-token/{revoked}").status_code == 404


def test_existing_user_accepts_invitation(world) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    token = invite(lucia, lucia.spaces["Familia"], "viewer")
    response = javier.post(f"/api/v1/invitations/by-token/{token}/accept", json={})
    assert response.json() == {"stage": "full", "space_id": lucia.spaces["Familia"]}
    roles = {s["name"]: s["role"] for s in javier.get("/api/v1/spaces").json()}
    assert roles == {"Pareja": "owner", "Familia": "viewer"}


def test_spaces_are_isolated(world) -> None:  # type: ignore[no-untyped-def]
    """Nada de un espacio es visible para quien no es miembro, tampoco para el administrador."""
    javier, lucia = world
    familia = lucia.spaces["Familia"]
    assert familia not in {s["id"] for s in javier.get("/api/v1/spaces").json()}
    for method, url, body in [
        ("get", f"/api/v1/spaces/{familia}", None),
        ("patch", f"/api/v1/spaces/{familia}", {"name": "Mía"}),
        ("get", f"/api/v1/spaces/{familia}/members", None),
        ("get", f"/api/v1/spaces/{familia}/invitations", None),
        ("post", f"/api/v1/spaces/{familia}/invitations", {"role": "owner"}),
        ("patch", f"/api/v1/spaces/{familia}/members/{uuid.uuid4()}", {"role": "owner"}),
        ("delete", f"/api/v1/spaces/{familia}/members/{uuid.uuid4()}", None),
        ("get", f"/api/v1/spaces/{uuid.uuid4()}", None),
    ]:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(javier, method)(url, **kwargs)
        assert response.status_code == 404, (method, url, response.text)
        assert "Familia" not in response.text
    assert javier.patch("/api/v1/me", json={"last_space_id": familia}).status_code == 404


def test_role_matrix(world, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    pareja = javier.spaces["Pareja"]
    lector = join(new_client(), engine, invite(javier, pareja, "viewer"), "lector")

    # Lector: ve, pero no cambia nada
    assert lector.get(f"/api/v1/spaces/{pareja}/members").status_code == 200
    assert lector.post(f"/api/v1/spaces/{pareja}/invitations", json={"role": "viewer"}).status_code == 403
    assert lector.patch(f"/api/v1/spaces/{pareja}", json={"name": "X"}).status_code == 403
    # Colaboradora: no gestiona miembros ni el espacio
    assert lucia.patch(f"/api/v1/spaces/{pareja}", json={"name": "X"}).status_code == 403
    assert lucia.post(f"/api/v1/spaces/{pareja}/invitations", json={"role": "viewer"}).status_code == 403
    assert (
        lucia.patch(f"/api/v1/spaces/{pareja}/members/{_id(javier)}", json={"role": "viewer"}).status_code
        == 403
    )
    # Propietario: todo
    assert javier.patch(f"/api/v1/spaces/{pareja}", json={"name": "Nosotros"}).json()["name"] == "Nosotros"
    assert (
        javier.patch(f"/api/v1/spaces/{pareja}/members/{_id(lucia)}", json={"role": "owner"}).status_code
        == 204
    )
    # Cualquiera puede salir; nunca puede quedarse un espacio sin propietario
    assert lector.delete(f"/api/v1/spaces/{pareja}/members/{_id(lector)}").status_code == 204
    assert lector.get(f"/api/v1/spaces/{pareja}").status_code == 404
    assert (
        lucia.delete(f"/api/v1/spaces/{lucia.spaces['Familia']}/members/{_id(lucia)}").json()["code"]
        == "last_owner"
    )
    assert (
        lucia.patch(
            f"/api/v1/spaces/{lucia.spaces['Familia']}/members/{_id(lucia)}", json={"role": "viewer"}
        ).status_code
        == 409
    )


def test_archive_space(world) -> None:  # type: ignore[no-untyped-def]
    javier, _ = world
    pareja = javier.spaces["Pareja"]
    assert javier.patch(f"/api/v1/spaces/{pareja}", json={"archived": True}).json()["archived"] is True
    assert javier.get("/api/v1/spaces").json()[0]["archived"] is True


def _id(person: Person) -> str:
    return str(person.get("/api/v1/me").json()["id"])


def test_admin_manages_people(world, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    users = {u["username"]: u for u in javier.get("/api/v1/admin/users").json()}
    assert users["lucia"]["spaces"] == 2 and users["lucia"]["has_totp"]
    assert lucia.get("/api/v1/admin/users").status_code == 403

    lucia_id = users["lucia"]["id"]
    assert javier.post(f"/api/v1/admin/users/{lucia_id}/active", json={"active": False}).status_code == 204
    assert lucia.get("/api/v1/me").status_code == 401
    assert (
        lucia.post("/api/v1/auth/login", json={"username": "lucia", "password": PASSWORD}).status_code == 401
    )
    assert javier.post(f"/api/v1/admin/users/{_id(javier)}/active", json={"active": False}).status_code == 409
    javier.post(f"/api/v1/admin/users/{lucia_id}/active", json={"active": True})

    # Restablecer acceso, también el segundo factor
    link = javier.post(f"/api/v1/admin/users/{lucia_id}/reset", json={"reset_totp": True}).json()["url"]
    token = link.rsplit("/", 1)[1]
    anon = new_client()
    assert anon.get(f"/api/v1/password-resets/{token}").json() == {"username": "lucia", "reset_totp": True}
    assert anon.post(f"/api/v1/password-resets/{token}", json={"password": "corta"}).status_code == 422
    assert (
        anon.post(f"/api/v1/password-resets/{token}", json={"password": "frase nueva de lucía"}).status_code
        == 200
    )
    assert (
        anon.post(f"/api/v1/password-resets/{token}", json={"password": "frase nueva de lucía"}).status_code
        == 404
    )
    fresh = Person(new_client(), "lucia", password="frase nueva de lucía")
    assert login(fresh, engine) == "enroll"

    # Invitación sin espacio
    url = javier.post("/api/v1/admin/invitations").json()["url"]
    sin_espacio = join(new_client(), engine, url.rsplit("/", 1)[1], "suelto")
    assert sin_espacio.spaces == {}


def test_admin_revokes_sessions(world) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    assert javier.post(f"/api/v1/admin/users/{_id(lucia)}/revoke-sessions").status_code == 204
    assert lucia.get("/api/v1/me").status_code == 401


def test_audit_and_notices(world, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    lucia.post("/api/v1/auth/logout")
    for _ in range(3):
        lucia.post("/api/v1/auth/login", json={"username": "lucia", "password": "no es la buena!"})
    page = javier.get("/api/v1/admin/audit", params={"limit": 5}).json()
    assert len(page["items"]) == 5 and page["next_cursor"]
    following = javier.get("/api/v1/admin/audit", params={"cursor": page["next_cursor"]}).json()
    assert {i["id"] for i in following["items"]}.isdisjoint({i["id"] for i in page["items"]})
    failed = javier.get("/api/v1/admin/audit", params={"action": "auth.login_failed"}).json()["items"]
    assert len(failed) == 3 and failed[0]["detail"]["username"] == "lucia"
    actions = {i["action"] for i in javier.get("/api/v1/admin/audit", params={"limit": 500}).json()["items"]}
    assert {
        "setup.completed",
        "space.created",
        "invitation.created",
        "invitation.accepted",
        "auth.totp_enabled",
    } <= actions

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_failures (key, at) "
                "SELECT 'ip:203.0.113.9', now() FROM generate_series(1, 25)"
            )
        )
    from sqlalchemy.orm import Session

    from app.services.notices import raise_notice

    with Session(engine) as db:
        for _ in range(2):  # el mismo aviso abierto no se duplica
            raise_notice(db, "test", "Aviso de prueba", dedup_key="prueba")
        db.commit()
    notices = javier.get("/api/v1/admin/notices").json()
    assert [n["message"] for n in notices].count("Aviso de prueba") == 1
    assert javier.post(f"/api/v1/admin/notices/{notices[0]['id']}/ack").status_code == 204
    assert len(javier.get("/api/v1/admin/notices").json()) == len(notices) - 1
    assert totp_code  # importado para otras pruebas


def test_admin_deletes_account(world, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    javier, lucia = world
    lucia_id = _id(lucia)
    # Lucía es la única propietaria de «Familia»: primero hay que nombrar a otra persona
    assert javier.delete(f"/api/v1/admin/users/{lucia_id}").json()["code"] == "last_owner"
    token = invite(lucia, lucia.spaces["Familia"], "owner")
    javier.post(f"/api/v1/invitations/by-token/{token}/accept", json={})
    assert javier.delete(f"/api/v1/admin/users/{_id(javier)}").json()["code"] == "self"
    assert javier.delete(f"/api/v1/admin/users/{lucia_id}").status_code == 204
    assert lucia.get("/api/v1/me").status_code == 401
    assert "lucia" not in {u["username"] for u in javier.get("/api/v1/admin/users").json()}
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'user.deleted'")).scalar_one()
            == 1
        )
