"""Live smoke: dummy project, generate scope_analysis, poll, audit checks."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

import httpx

BASE = "http://127.0.0.1:8080"


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    from app.config import get_settings

    settings = get_settings()
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        token = login(client, email, password)
        headers = {"Authorization": f"Bearer {token}"}

        data = {
            "name": f"Fictional Pilot {uuid.uuid4().hex[:8]}",
            "client_name": "Contoso Example Ltd (fictional)",
            "kind": "email",
            "received_at": datetime.now(UTC).isoformat(),
            "received_from": "fictional.client@example.test",
            "subject": "Imaginary widget portal phase 1",
            "body": (
                "Fictional request: build a training-only customer portal for "
                "order tracking and invoice download. Integrate with ExampleERP. "
                "Mobile-friendly. This is synthetic test data."
            ),
        }
        files = [
            (
                "files",
                (
                    "dummy-notes.txt",
                    b"Fictional attachment: admins need CSV export of orders.",
                    "text/plain",
                ),
            )
        ]
        r = client.post("/projects", data=data, files=files, headers=headers)
        print("create_project", r.status_code)
        r.raise_for_status()
        project = r.json()["project"]
        pid = project["id"]

        steps = client.get(f"/projects/{pid}/steps", headers=headers)
        print("get_steps", steps.status_code)
        steps.raise_for_status()
        s0 = steps.json()["steps"][0]
        print(f"step1 status={s0['status']} can_generate={s0['can_generate']}")

        t0 = time.monotonic()
        gen = client.post(
            f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
        )
        print("generate", gen.status_code)
        gen.raise_for_status()
        version_id = gen.json()["version"]["id"]

        status = "queued"
        for _ in range(120):
            detail = client.get(f"/step-versions/{version_id}", headers=headers)
            detail.raise_for_status()
            status = detail.json()["status"]
            if status in ("in_review", "failed"):
                break
            time.sleep(1)
        elapsed = time.monotonic() - t0
        detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
        print(
            f"final_status={status} duration_s={elapsed:.1f} "
            f"tokens_in={detail.get('tokens_in')} tokens_out={detail.get('tokens_out')}"
        )

        client.get(
            f"/step-versions/{version_id}/prompt",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Admin has prompt.view
        prompt_ok = client.get(f"/step-versions/{version_id}/prompt", headers=headers)
        print("prompt_admin", prompt_ok.status_code)

        gen2 = client.post(
            f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
        )
        print("second_generate", gen2.status_code, gen2.json().get("detail"))

        audit = client.get(
            f"/projects/{pid}/audit",
            headers=headers,
        )
        if audit.status_code == 404:
            print("audit: use psql for actions (no list endpoint yet)")
        else:
            print("audit_list", audit.status_code)

    # psql audit actions
    db_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "")
    user_pass, host_db = db_url.split("@", 1)
    user, password_db = user_pass.split(":", 1)
    host_port, dbname = host_db.split("/", 1)
    host, port = host_port.split(":")
    env = {"PGPASSWORD": password_db}
    sql = (
        "SELECT action, actor_email, metadata::text "
        f"FROM audit_log WHERE project_id = '{pid}' "
        "AND action LIKE 'step.%' ORDER BY occurred_at;"
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
    sql2 = (
        "SELECT length(assembled_prompt) FROM step_versions "
        f"WHERE id = '{version_id}';"
    )
    out2 = subprocess.run(
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
            sql2,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    print("--- assembled_prompt length ---")
    print(out2.stdout)
    return 0 if status == "in_review" else 1


if __name__ == "__main__":
    sys.exit(main())
