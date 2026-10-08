"""Live smoke: request-changes, approve, self-approval policy (Lead user)."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

import httpx

BASE = "http://127.0.0.1:8080"
LEAD_EMAIL = "lead-live@example.test"
LEAD_PASSWORD = "lead-live-pass-12"


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_lead(client: httpx.Client, admin_headers: dict[str, str]) -> dict[str, str]:
    roles = client.get("/roles", headers=admin_headers)
    roles.raise_for_status()
    lead_role = next(r for r in roles.json() if r["name"] == "Lead")
    created = client.post(
        "/users",
        headers=admin_headers,
        json={
            "email": LEAD_EMAIL,
            "full_name": "Live Lead",
            "password": LEAD_PASSWORD,
            "role_ids": [lead_role["id"]],
            "is_active": True,
        },
    )
    if created.status_code not in (201, 409):
        created.raise_for_status()
    token = login(client, LEAD_EMAIL, LEAD_PASSWORD)
    return {"Authorization": f"Bearer {token}"}


def poll_in_review(client: httpx.Client, version_id: str, headers: dict[str, str]) -> str:
    status = "queued"
    for _ in range(180):
        detail = client.get(f"/step-versions/{version_id}", headers=headers)
        detail.raise_for_status()
        status = detail.json()["status"]
        if status in ("in_review", "failed"):
            return status
        time.sleep(1)
    return status


def main() -> int:
    from app.config import get_settings

    settings = get_settings()
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        admin_token = login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lead_headers = ensure_lead(client, admin_headers)

        put = client.put(
            "/settings",
            headers=admin_headers,
            json={"allow_self_approval": False},
        )
        print("global_self_approval_off", put.status_code)

        data = {
            "name": f"Approval Pilot {uuid.uuid4().hex[:8]}",
            "client_name": "Fictional Co",
            "kind": "email",
            "received_at": datetime.now(UTC).isoformat(),
            "received_from": "fictional@example.test",
            "subject": "Scope review test",
            "body": "Synthetic scope for approval flow testing only.",
        }
        files = [
            (
                "files",
                ("notes.txt", b"Fictional attachment.", "text/plain"),
            )
        ]
        created = client.post("/projects", data=data, files=files, headers=lead_headers)
        print("create_project", created.status_code)
        created.raise_for_status()
        pid = created.json()["project"]["id"]

        gen = client.post(
            f"/projects/{pid}/steps/scope_analysis/generate", headers=lead_headers
        )
        print("generate", gen.status_code)
        gen.raise_for_status()
        v1 = gen.json()["version"]["id"]
        status = poll_in_review(client, v1, lead_headers)
        print("v1_status", status)
        if status != "in_review":
            return 1

        rc = client.post(
            f"/step-versions/{v1}/request-changes",
            headers=lead_headers,
            json={"instructions": "Add more explicit out-of-scope items."},
        )
        print("request_changes", rc.status_code)
        rc.raise_for_status()
        v2 = rc.json()["version"]["id"]
        status2 = poll_in_review(client, v2, lead_headers)
        print("v2_status", status2)
        if status2 != "in_review":
            return 1

        blocked = client.post(
            f"/step-versions/{v2}/approve", headers=lead_headers, json={}
        )
        print("lead_self_approve_blocked", blocked.status_code, blocked.json().get("detail"))

        ok = client.post(
            f"/step-versions/{v2}/approve", headers=admin_headers, json={"comment": "LGTM"}
        )
        print("admin_approve", ok.status_code)
        if ok.status_code != 200:
            return 1
        print("self_approved", ok.json()["approval"]["self_approved"])

    db_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "")
    user_pass, host_db = db_url.split("@", 1)
    user, password_db = user_pass.split(":", 1)
    host_port, dbname = host_db.split("/", 1)
    host, port = host_port.split(":")
    env = {"PGPASSWORD": password_db}
    sql = (
        "SELECT action, metadata::text FROM audit_log "
        f"WHERE project_id = '{pid}' AND action LIKE 'step.%' "
        "ORDER BY occurred_at;"
    )
    out = subprocess.run(
        [
            "psql",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            dbname,
            "-c",
            sql,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    print("--- audit step actions ---")
    print(out.stdout)
    return 0 if blocked.status_code == 403 and ok.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
