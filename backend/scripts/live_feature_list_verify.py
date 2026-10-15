"""Live smoke: dummy project through Feature List. Use only fictional data."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from io import BytesIO

import httpx
from docx import Document

BASE = "http://127.0.0.1:8080"


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def poll_version(client: httpx.Client, headers: dict[str, str], version_id: str) -> dict:
    status = "queued"
    detail: dict = {}
    for _ in range(120):
        resp = client.get(f"/step-versions/{version_id}", headers=headers)
        resp.raise_for_status()
        detail = resp.json()
        status = detail["status"]
        if status in {"in_review", "failed", "approved"}:
            return detail
        time.sleep(2)
    raise RuntimeError(f"timed out waiting for {version_id}, last status={status}")


def main() -> int:
    from app.config import get_settings

    settings = get_settings()
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD

    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        token = login(client, email, password)
        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "name": f"Fictional Feature Pilot {uuid.uuid4().hex[:8]}",
            "client_name": "Contoso Example Ltd (fictional)",
            "kind": "email",
            "received_at": datetime.now(UTC).isoformat(),
            "received_from": "fictional.client@example.test",
            "subject": "Imaginary widget portal phase 1",
            "body": (
                "Fictional request: build a training-only customer portal for "
                "order tracking and invoice download. Integrate with ExampleERP. "
                "Admins need CSV export. This is synthetic test data."
            ),
        }
        r = client.post("/projects", data=data, headers=headers)
        print("create_project", r.status_code)
        r.raise_for_status()
        pid = r.json()["project"]["id"]

        steps = client.get(f"/projects/{pid}/steps", headers=headers).json()["steps"]
        fl = next(s for s in steps if s["key"] == "feature_list")
        print("step3_before", fl["status"], fl["blocked_reason"])

        s1 = client.post(
            f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
        )
        print("generate_scope", s1.status_code)
        s1.raise_for_status()
        scope = poll_version(client, headers, s1.json()["version"]["id"])
        print("scope", scope["status"])
        client.post(
            f"/step-versions/{scope['id']}/approve", headers=headers, json={}
        ).raise_for_status()

        s2 = client.post(f"/projects/{pid}/steps/gap_analysis/generate", headers=headers)
        print("generate_gap", s2.status_code)
        s2.raise_for_status()
        gap = poll_version(client, headers, s2.json()["version"]["id"])
        print("gap", gap["status"], "gaps", len((gap.get("content") or {}).get("gaps") or []))
        client.post(
            f"/step-versions/{gap['id']}/approve", headers=headers, json={}
        ).raise_for_status()

        steps = client.get(f"/projects/{pid}/steps", headers=headers).json()["steps"]
        fl = next(s for s in steps if s["key"] == "feature_list")
        print("step3_ready", fl["status"], fl["can_generate"])

        notes = "Fictional client confirmed ExampleERP v4 and CSV export for admins."
        s3 = client.post(
            f"/projects/{pid}/steps/feature_list/generate",
            headers=headers,
            json={"inputs": {"team_notes": notes}},
        )
        print("generate_features", s3.status_code)
        s3.raise_for_status()
        v1 = poll_version(client, headers, s3.json()["version"]["id"])
        print("feature_v1", v1["status"])
        content = v1["content"] or {}
        features = content.get("features") or []
        modules = content.get("modules") or []
        print("modules", [m.get("name") for m in modules])
        print("feature_count", len(features))
        print("stats", content.get("stats"))
        print("validation_notes", (v1.get("inputs") or {}).get("validation_notes"))
        for feat in features[:5]:
            print(
                feat.get("id"),
                feat.get("title"),
                feat.get("priority"),
                feat.get("origin"),
                feat.get("depends_on_ids"),
                feat.get("linked_gap_refs"),
            )

        rev = client.post(
            f"/step-versions/{v1['id']}/request-changes",
            headers=headers,
            json={"instructions": "Add a fictional notification feature for order status."},
        )
        print("request_changes", rev.status_code)
        rev.raise_for_status()
        v2 = poll_version(client, headers, rev.json()["version"]["id"])
        print("feature_v2", v2["status"], "count", len((v2.get("content") or {}).get("features") or []))
        print(
            "notes_carried",
            (v2.get("inputs") or {}).get("user_inputs", {}).get("team_notes") == notes,
        )
        client.post(
            f"/step-versions/{v2['id']}/approve", headers=headers, json={}
        ).raise_for_status()

        dl = client.get(
            f"/step-versions/{v2['id']}/download?format=docx", headers=headers
        )
        print("docx", dl.status_code, len(dl.content))
        dl.raise_for_status()
        doc = Document(BytesIO(dl.content))
        text = "\n".join(p.text for p in doc.paragraphs)
        print("docx_has_F-001", "F-001" in text)
        print("docx_has_priority", "Priority:" in text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAILED", type(exc).__name__, exc)
        raise SystemExit(1) from exc
