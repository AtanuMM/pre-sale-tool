from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.main import app as fastapi_app
from app.models.projects import Project
from app.models.system import AuditLog
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from app.services.audit import AuditAction, record_audit
from app.services.file_validation import ALLOWED_UPLOAD_EXTENSIONS
from app.services.storage import (
    STORAGE_UNAVAILABLE_DETAIL,
    StorageError,
    ensure_bucket,
    get_s3_client,
    put_file,
)
from tests.db_utils import reset_rbac_test_data
from tests.fixtures.file_samples import (
    fake_pdf_exe,
    sample_pdf_no_text_layer,
    sample_txt,
)


def _minio_available() -> bool:
    settings = get_settings()
    client = get_s3_client(settings=settings)
    try:
        client.head_bucket(Bucket=settings.S3_TEST_BUCKET)
        return True
    except ClientError:
        try:
            ensure_bucket(client=client, bucket=settings.S3_TEST_BUCKET)
            return True
        except ClientError:
            return False


MINIO = _minio_available()
pytestmark_storage = pytest.mark.skipif(not MINIO, reason="MinIO not available")


@pytest.fixture(autouse=True)
def _projects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "projects-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "projects-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Projects Admin")
    if MINIO:
        monkeypatch.setenv("S3_BUCKET", get_settings().S3_TEST_BUCKET)
        monkeypatch.setenv("S3_PATH_STYLE", "true")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_db(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _projects_env: None,
) -> tuple[sessionmaker[Session], Settings]:
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    if MINIO:
        ensure_bucket(bucket=settings.S3_TEST_BUCKET)
    return factory, settings


@pytest.fixture
def client(seeded_session, _projects_env: None) -> TestClient:
    reset_engine()
    return TestClient(fastapi_app)


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(client: TestClient, settings: Settings) -> dict[str, str]:
    token = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {token}"}


def _received_at_now() -> str:
    return datetime.now(UTC).isoformat()


def _create_project_multipart(
    client: TestClient,
    headers: dict[str, str],
    *,
    files: list[tuple[str, bytes, str]] | None = None,
    body: str = "Initial scope body",
    name: str = "Acme Portal",
    client_name: str = "Acme Corp",
) -> dict:
    data = {
        "name": name,
        "client_name": client_name,
        "kind": "email",
        "received_at": _received_at_now(),
        "received_from": "client@acme.com",
        "subject": "Scope request",
        "body": body,
    }
    multipart_files = []
    if files:
        for filename, content, mime in files:
            multipart_files.append(("files", (filename, io.BytesIO(content), mime)))
    resp = client.post("/projects", data=data, files=multipart_files, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _viewer_headers(client: TestClient, factory: sessionmaker[Session]) -> dict[str, str]:
    with factory() as session:
        from app.models.auth import Role, User, UserRole
        from app.security.passwords import hash_password

        role = session.scalar(select(Role).where(Role.name == "Viewer"))
        assert role is not None
        user = User(
            email="viewer-only@projects.test",
            full_name="Viewer Only",
            password_hash=hash_password("viewer-pass-12"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.commit()
    token = _login(client, "viewer-only@projects.test", "viewer-pass-12")
    return {"Authorization": f"Bearer {token}"}


PERMISSION_ENDPOINTS = (
    ("POST", "/projects", "project.create"),
    ("GET", "/projects", "project.view"),
    ("GET", "/projects/{pid}", "project.view"),
    ("GET", "/projects/{pid}/overview", "project.view"),
    ("POST", "/projects/{pid}/inputs", "input.add"),
    ("GET", "/projects/{pid}/files/{fid}/download", "project.view"),
    ("GET", "/projects/{pid}/files/{fid}/text", "project.view"),
    ("PATCH", "/projects/{pid}/settings", "settings.manage"),
    ("POST", "/projects/{pid}/archive", "project.archive"),
    ("POST", "/projects/{pid}/restore", "project.archive"),
)


@pytest.mark.usefixtures("_projects_env")
class TestProjectsPermissions:
    @pytest.mark.parametrize("method,path,permission", PERMISSION_ENDPOINTS)
    def test_requires_auth(self, client: TestClient, method: str, path: str, permission: str) -> None:
        pid, fid = uuid.uuid4(), uuid.uuid4()
        url = path.format(pid=pid, fid=fid)
        resp = client.request(method, url)
        assert resp.status_code == 401

    @pytestmark_storage
    def test_viewer_forbidden_on_create(
        self, client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
    ) -> None:
        factory, _settings = seeded_session
        viewer = _viewer_headers(client, factory)
        data = {
            "name": "X",
            "client_name": "Y",
            "kind": "email",
            "received_at": _received_at_now(),
            "body": "text",
        }
        resp = client.post("/projects", data=data, headers=viewer)
        assert resp.status_code == 403


@pytestmark_storage
def test_create_with_attachments_and_overview(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    created = _create_project_multipart(
        client,
        headers,
        files=[
            ("notes.txt", sample_txt(), "text/plain"),
            ("scan.pdf", sample_pdf_no_text_layer(), "application/pdf"),
        ],
    )
    assert created["project"]["name"] == "Acme Portal"
    assert len(created["files"]) == 2
    statuses = {f["original_name"]: f["extraction_status"] for f in created["files"]}
    assert statuses["notes.txt"] == "ok"
    assert statuses["scan.pdf"] == "empty"

    pid = created["project"]["id"]
    overview = client.get(f"/projects/{pid}/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert len(body["inputs"]) == 1
    assert body["inputs"][0]["is_followup"] is False
    assert body["inputs"][0]["body"] == "Initial scope body"
    assert len(body["timeline"]) >= 2
    assert "storage_key" not in overview.text

    detail = client.get(f"/projects/{pid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["inputs"][0]["body"] == "Initial scope body"
    assert created["input"]["body"] == "Initial scope body"


@pytestmark_storage
def test_bad_requests_leave_no_rows(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings], migrated_test_engine
) -> None:
    headers = _auth(client, seeded_session[1])
    factory = seeded_session[0]
    before_projects = _count_projects(factory)

    data_base = {
        "name": "Bad",
        "client_name": "Co",
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "",
    }

    many = [("files", (f"f{i}.txt", io.BytesIO(sample_txt()), "text/plain")) for i in range(11)]
    resp = client.post("/projects", data=data_base, files=many, headers=headers)
    assert resp.status_code == 422
    assert _count_projects(factory) == before_projects

    huge = b"x" * (get_settings().MAX_UPLOAD_FILE_BYTES + 1)
    resp2 = client.post(
        "/projects",
        data={**data_base, "body": "ok"},
        files=[("files", ("big.bin", io.BytesIO(huge), "application/octet-stream"))],
        headers=headers,
    )
    assert resp2.status_code == 413

    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    resp3 = client.post(
        "/projects",
        data={**data_base, "received_at": future, "body": "ok"},
        headers=headers,
    )
    assert resp3.status_code == 422

    resp4 = client.post("/projects", data={**data_base}, headers=headers)
    assert resp4.status_code == 422

    resp5 = client.post(
        "/projects",
        data={**data_base, "body": "ok"},
        files=[("files", ("evil.pdf", io.BytesIO(fake_pdf_exe()), "application/pdf"))],
        headers=headers,
    )
    assert resp5.status_code == 422


@pytestmark_storage
def test_db_failure_rolls_back_storage(
    client: TestClient,
    seeded_session: tuple[sessionmaker[Session], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client, seeded_session[1])
    settings = get_settings()
    keys_before = _list_upload_keys(settings)
    factory = seeded_session[0]
    with factory() as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditLog))

    def boom(*args, **kwargs):
        if kwargs.get("action") == AuditAction.INPUT_ADDED:
            raise RuntimeError("simulated db failure")
        return record_audit(*args, **kwargs)

    monkeypatch.setattr("app.services.project_intake.record_audit", boom)

    data = {
        "name": "Rollback",
        "client_name": "Co",
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "content",
    }
    files = [("files", ("a.txt", io.BytesIO(sample_txt()), "text/plain"))]
    soft = TestClient(fastapi_app, raise_server_exceptions=False)
    resp = soft.post("/projects", data=data, files=files, headers=headers)
    assert resp.status_code == 500

    assert _count_projects(factory) == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditLog)) == audit_before
        project_audits = session.scalars(
            select(AuditLog).where(
                AuditLog.action.in_(
                    (AuditAction.PROJECT_CREATED, AuditAction.INPUT_ADDED)
                )
            )
        ).all()
        assert project_audits == []

    keys_after = _list_upload_keys(settings)
    assert keys_after == keys_before


@pytestmark_storage
def test_followup_and_archived_conflict(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    created = _create_project_multipart(client, headers, files=[("a.txt", sample_txt(), "text/plain")])
    pid = created["project"]["id"]

    follow_data = {
        "name": created["project"]["name"],
        "client_name": created["project"]["client_name"],
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "Follow-up body",
    }
    resp = client.post(f"/projects/{pid}/inputs", data=follow_data, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["input"]["is_followup"] is True
    assert resp.json()["input"]["body"] == "Follow-up body"

    overview = client.get(f"/projects/{pid}/overview", headers=headers).json()
    bodies = {inp["is_followup"]: inp["body"] for inp in overview["inputs"]}
    assert bodies[False] == "Initial scope body"
    assert bodies[True] == "Follow-up body"

    client.post(f"/projects/{pid}/archive", headers=headers)
    blocked = client.post(f"/projects/{pid}/inputs", data=follow_data, headers=headers)
    assert blocked.status_code == 409


@pytestmark_storage
def test_download_and_cross_project_404(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    original = sample_txt()
    created = _create_project_multipart(
        client, headers, files=[("dl.txt", original, "text/plain")]
    )
    pid = created["project"]["id"]
    fid = created["files"][0]["id"]

    dl = client.get(f"/projects/{pid}/files/{fid}/download", headers=headers)
    assert dl.status_code == 200
    assert dl.content == original
    assert dl.headers.get("x-content-type-options") == "nosniff"
    assert "attachment" in dl.headers.get("content-disposition", "")

    other = _create_project_multipart(client, headers, body="other")
    wrong = client.get(
        f"/projects/{other['project']['id']}/files/{fid}/download",
        headers=headers,
    )
    assert wrong.status_code == 404

    factory = seeded_session[0]
    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.DOCUMENT_DOWNLOADED)
        ).all()
        assert len(audits) == 1
        assert audits[0].meta.get("file_id") == fid


@pytestmark_storage
def test_settings_override_and_effective(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    created = _create_project_multipart(client, headers, body="only body")
    pid = created["project"]["id"]

    for value, expected in [(False, False), (True, True), (None, True)]:
        patch = client.patch(
            f"/projects/{pid}/settings",
            headers=headers,
            json={"allow_self_approval": value},
        )
        assert patch.status_code == 200
        assert patch.json()["allow_self_approval"] == value
        overview = client.get(f"/projects/{pid}/overview", headers=headers).json()
        assert overview["effective_allow_self_approval"] is expected

    factory = seeded_session[0]
    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_SETTINGS_CHANGED)
        ).all()
        assert len(audits) >= 3


@pytestmark_storage
def test_archive_restore_completed(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    created = _create_project_multipart(client, headers, body="body")
    pid = created["project"]["id"]
    factory = seeded_session[0]
    with factory() as session:
        project = session.get(Project, uuid.UUID(pid))
        assert project is not None
        project.status = "completed"
        project.completed_at = datetime.now(UTC)
        session.commit()

    client.post(f"/projects/{pid}/archive", headers=headers)
    restored = client.post(f"/projects/{pid}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"


@pytestmark_storage
def test_input_added_audit_has_no_client_text(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    secret = "super-secret-client-body-text"
    _create_project_multipart(client, headers, body=secret, files=[("a.txt", sample_txt(), "text/plain")])
    factory = seeded_session[0]
    with factory() as session:
        row = session.scalar(
            select(AuditLog).where(AuditLog.action == AuditAction.INPUT_ADDED)
        )
        assert row is not None
        blob = json.dumps(row.meta)
        assert secret not in blob
        assert "subject" not in row.meta or "Scope request" not in json.dumps(row.meta.get("subject"))


def test_list_response_excludes_input_body(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    _create_project_multipart(client, headers, body="secret-list-body-should-not-appear")
    listed = client.get("/projects", headers=headers)
    assert listed.status_code == 200
    data = listed.json()
    assert data["items"]
    for item in data["items"]:
        assert "body" not in item
    assert "secret-list-body-should-not-appear" not in listed.text


def test_intake_limits_requires_auth(client: TestClient) -> None:
    resp = client.get("/projects/limits")
    assert resp.status_code == 401


def test_intake_limits_returns_settings(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    settings = get_settings()
    resp = client.get("/projects/limits", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_file_bytes"] == settings.MAX_UPLOAD_FILE_BYTES
    assert data["max_files_per_input"] == settings.MAX_FILES_PER_INPUT
    assert data["max_extracted_chars"] == settings.MAX_EXTRACTED_TEXT_CHARS
    assert data["allowed_extensions"] == list(ALLOWED_UPLOAD_EXTENSIONS)


def test_intake_limits_not_shadowed_by_project_id_route(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    resp = client.get("/projects/limits", headers=headers)
    assert resp.status_code == 200
    assert "max_file_bytes" in resp.json()


@pytestmark_storage
def test_list_search_and_filter(
    client: TestClient, seeded_session: tuple[sessionmaker[Session], Settings]
) -> None:
    headers = _auth(client, seeded_session[1])
    _create_project_multipart(
        client, headers, name="Alpha Search", client_name="Alpha Co", body="a"
    )
    _create_project_multipart(
        client, headers, name="Beta Other", client_name="Beta Co", body="b"
    )
    listed = client.get("/projects", headers=headers, params={"search": "alpha"})
    assert listed.status_code == 200
    data = listed.json()
    assert data["total"] >= 1
    assert any("Alpha" in i["name"] for i in data["items"])

    archived = _create_project_multipart(client, headers, name="To Archive", client_name="Z", body="c")
    client.post(f"/projects/{archived['project']['id']}/archive", headers=headers)
    active_only = client.get("/projects", headers=headers, params={"status": "active"})
    assert all(i["status"] == "active" for i in active_only.json()["items"])


def _count_projects(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(Project)) or 0


@pytestmark_storage
def test_second_put_failure_deletes_first_object_and_no_db_rows(
    client: TestClient,
    seeded_session: tuple[sessionmaker[Session], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    headers = _auth(client, settings)
    factory = seeded_session[0]
    before_projects = _count_projects(factory)
    first_key: list[str] = []

    real_put = put_file

    def fake_put(body, content_type, **kwargs):
        if not first_key:
            result = real_put(body, content_type, **kwargs)
            first_key.append(result.storage_key)
            return result
        raise StorageError("Storage put_object failed")

    monkeypatch.setattr("app.services.file_service.put_file", fake_put)

    data = {
        "name": "Two File Fail",
        "client_name": "Co",
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "ok",
    }
    files = [
        ("files", ("a.pdf", io.BytesIO(sample_pdf_no_text_layer()), "application/pdf")),
        ("files", ("b.pdf", io.BytesIO(sample_pdf_no_text_layer()), "application/pdf")),
    ]
    resp = client.post("/projects", data=data, files=files, headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == STORAGE_UNAVAILABLE_DETAIL
    assert _count_projects(factory) == before_projects
    assert len(first_key) == 1
    s3 = get_s3_client(settings=settings)
    with pytest.raises(ClientError):
        s3.head_object(Bucket=settings.S3_BUCKET, Key=first_key[0])


def test_storage_put_failure_returns_503_not_413(
    client: TestClient,
    seeded_session: tuple[sessionmaker[Session], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client, seeded_session[1])

    def fail_put(*args, **kwargs):
        raise StorageError("Storage put_object failed")

    monkeypatch.setattr("app.services.file_service.put_file", fail_put)

    data = {
        "name": "Storage Down",
        "client_name": "Co",
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "ok",
    }
    files = [("files", ("a.txt", io.BytesIO(sample_txt()), "text/plain"))]
    resp = client.post("/projects", data=data, files=files, headers=headers)
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"] == STORAGE_UNAVAILABLE_DETAIL
    assert "put_object" not in body["detail"]


def test_oversize_upload_returns_413(
    client: TestClient,
    seeded_session: tuple[sessionmaker[Session], Settings],
) -> None:
    headers = _auth(client, seeded_session[1])
    factory = seeded_session[0]
    before = _count_projects(factory)
    huge = b"x" * (get_settings().MAX_UPLOAD_FILE_BYTES + 1)
    data = {
        "name": "Huge",
        "client_name": "Co",
        "kind": "email",
        "received_at": _received_at_now(),
        "body": "ok",
    }
    files = [("files", ("big.bin", io.BytesIO(huge), "application/octet-stream"))]
    resp = client.post("/projects", data=data, files=files, headers=headers)
    assert resp.status_code == 413
    assert "exceeds maximum size" in resp.json()["detail"]
    assert _count_projects(factory) == before


def _list_upload_keys(settings: Settings) -> set[str]:
    client = get_s3_client(settings=settings)
    keys: set[str] = set()
    token = None
    while True:
        kwargs = {"Bucket": settings.S3_BUCKET, "Prefix": "uploads/"}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            keys.add(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys
