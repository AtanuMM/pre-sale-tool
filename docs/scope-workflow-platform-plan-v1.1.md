# Scope Workflow Platform: Project Plan

Version 1.1, 5 October 2026. Owner: Atanu Paul (Technical Head, Matrix Media Solutions Pvt. Ltd.)
Working name: ScopeDesk (rename freely).

---

## Changes in v1.1

- Workflow is now **eight steps**: Sprint Plan added as step 7, required, before FRS (now step 8).
- Step versions now have a `source` (`generated`, `manual_edit`, `section_regen`). Inline editing and "redo one section or line with AI" are in v1 (new section 2.4).
- Reopen behaviour confirmed: downstream steps become `stale`, nothing is deleted.
- Draft downloads confirmed (with DRAFT marker).
- Self-approval is now a global setting **plus a per-project override**.
- File storage: S3 API from day one. MinIO in development, AWS S3 later.
- Full assembled prompts are stored, with versioned prompt templates.
- Follow-up client emails are stored but not fed into later steps in v1.
- Hosting: AWS, details deferred.
- Items marked **(proposal)** are my suggested defaults and still need your confirmation.

---

## 0. How to use this document in a new chat

Paste this whole file at the start of a new chat, then add one line saying which phase or task you are on. Suggested opener:

> I am building the platform described in the attached plan. I write the code myself and you guide me step by step: explain, review what I paste, point out bugs and design problems. Do not build whole modules for me unless I ask. I am currently on Phase __, task __.

**Working agreement (important):**
- Atanu writes the code. The assistant explains concepts, gives small targeted snippets only when asked, reviews pasted code, and flags risks.
- Plan before code: the assistant proposes the plan for a step and waits for an explicit "go" before any code.
- Work in small steps. Each step ends with something Atanu can run and check.
- The assistant must not claim code works unless it was actually run. Anything untested should be called untested.
- Verify current facts (model IDs, library APIs, free-tier limits) before relying on them. Do not rely on memory for these.
- Frontend changes are gated by `tsc --noEmit`.

---

## 1. Purpose

An internal web platform that takes a client's initial email or scope and walks it through a fixed, approval-gated chain of AI-assisted analysis and documentation steps. Every action is tracked in an audit trail. It replaces manual, scattered analysis and documentation work with one repeatable process.

**Primary users:** the technical head, business analysts, tech leads, reviewers and admins at Matrix Media.

**One project = one client engagement** (one initial email or scope document).

### Out of scope for v1
- Client-facing access or portals
- Multi-organisation (multi-tenant) support
- Real-time collaborative editing (two people editing the same document live)
- Payment, invoicing, or CRM features
- Mobile app
- Automatic inclusion of follow-up client emails in later steps

---

## 2. The workflow

Eight steps in a fixed order. Each step depends on the previous one being approved.

| # | Step key | Output document | Needs from the user before generating |
|---|----------|-----------------|---------------------------------------|
| 1 | `scope_analysis` | Scope Analysis | The initial email or scope (intake) |
| 2 | `gap_analysis` | Gap Analysis | Nothing extra |
| 3 | `feature_list` | Feature List | Nothing extra |
| 4 | `estimate` | Estimate (hours and weeks) | Team details (see section 9.4) |
| 5 | `sow` | Statement of Work | Nothing extra |
| 6 | `srs` | Software Requirements Specification | Nothing extra |
| 7 | `sprint_plan` | Sprint Plan | Sprint length and team capacity (see section 9.7) |
| 8 | `frs` | Functional Requirements Specification | Nothing extra |

When step 8 (FRS) is approved, the project is marked **completed**.

### 2.1 Step lifecycle

Each generation attempt, edit or section redo is a **step version**. A step version has one of these statuses:

`queued → generating → in_review → approved`
with side exits: `failed`, `changes_requested` (leads to a new version), `superseded`, `stale`.

Project-level step status (derived from the latest version):
- **locked**: previous step not approved yet
- **ready**: previous step approved, nothing generated yet
- **generating**
- **in_review**: output exists, awaiting approval or changes
- **approved**
- **stale**: an upstream step was reopened after this one was approved

Every version also has a `source`:
- `generated`: full AI generation (first attempt or after a change request)
- `manual_edit`: a person edited the content directly
- `section_regen`: AI redid one section or line, rest untouched

### 2.2 The interaction for each step
1. User clicks **Generate** (only when the step is ready).
2. System generates in the background; UI shows progress.
3. User reads the output.
4. Then any combination of:
   - **Request changes**: user types instructions; the system creates a **new version** from the previous one plus the instructions (full regeneration).
   - **Edit inline**: user changes text directly; saved as a new version (section 2.4).
   - **Redo a section or line with AI**: user selects part of the document and gives an instruction; only that part changes (section 2.4).
5. **Approve**: the version is pinned as the approved one; the next step unlocks.
6. User can download the document (see rules below).

### 2.3 Rules
- A step cannot be generated unless the previous step has an approved version.
- Only one generation may run per step at a time.
- Nothing overwrites. Every attempt, edit and section redo is a new version row. History is permanent.
- An approval pins one specific version. Later steps record which approved versions they were built from.
- **Download:** allowed from any version. Unapproved versions carry a visible "DRAFT, NOT APPROVED" marker in the document. (Decided.)
- **Reopening an approved step:** requires the `step.reopen` permission. Reopening marks all later approved steps as `stale`. Nothing is deleted. Stale steps must be regenerated and re-approved. Everything is audit-logged. (Decided.)
- **Self-approval:** governed by a global setting with a per-project override (section 4.4). Default for now: allowed.
- **Follow-up client emails** are stored as extra input rows but are not included in prompts for later steps in v1. Possible future version.

### 2.4 Editing and partial regeneration

**Inline edit**
- The editor is a structured, per-section form (one field per schema section), not free-form document editing. This keeps content valid against the step's Pydantic schema. (proposal)
- Saving creates a new version with `source = manual_edit`, `based_on_version_id` set, and status `in_review`.
- The saved content must pass the same schema validation as generated content.
- Edits are only allowed on the latest unapproved version. To change an approved step, reopen it first. (proposal)

**Redo one section or line with AI**
- The user picks a target inside the document and gives an instruction (for example "make this risk more specific" or "rewrite this paragraph shorter").
- The target is addressed by a path into the content JSON (for example `risks[2]` or `executive_summary`). A line is a path to a single string or list item.
- The engine sends the current document as context plus the instruction, asks the model to return only the replacement for that node (validated against that node's sub-schema), and splices it into a copy of the content.
- Saved as a new version with `source = section_regen` and `section_path` recorded.
- Rest of the document is guaranteed unchanged (the engine does the splice, not the model).

**Approval after edits:** approving a version that came from edits or section redos works the same way. The audit log shows the chain of versions (generated, then edits, then approved).

---

## 3. Intake (the starting point)

Creating a project means logging the initial client communication. Stored immutably.

Fields:
- Source type: email, document, meeting notes, other
- `received_at`: when the client sent it (entered by the user)
- `recorded_at`: when it was logged in the system (automatic)
- Received from (client contact name/email)
- Subject
- Body text (pasted)
- Attachments (uploaded files, text extracted for use in prompts)
- Logged by (user)

Follow-up client emails can be added later as additional input rows. They are appended, never edited. In v1 they are stored and shown on the project timeline but are **not** included in prompts for later steps.

---

## 4. Users, roles and permissions (RBAC)

### 4.1 Model
Permission-based RBAC. Roles are bundles of permissions. Code checks permissions, never role names. Enforcement is server-side only (the UI hides things for convenience, not security).

### 4.2 Permissions (initial list)
- `project.create`, `project.view`, `project.archive`
- `input.add`
- `step.generate`, `step.request_changes`, `step.edit`, `step.approve`, `step.reopen`
- `document.download`
- `reference.view`, `reference.manage`
- `template.view`, `template.manage`
- `prompt.view` (view stored assembled prompts)
- `audit.view`, `audit.export`
- `user.manage`, `role.manage`
- `settings.manage` (global and per-project settings)

### 4.3 Suggested starting roles
- **Admin**: everything
- **Lead / Approver**: create, generate, request changes, edit, approve, reopen, download, view audit, view prompts
- **Analyst**: create, generate, request changes, edit, download (approve only if self-approval is on)
- **Viewer**: view projects and download

### 4.4 Self-approval setting (global plus per project)
- Global setting `allow_self_approval` (boolean) in the `settings` table. Default **true** for now. Ideal future state is **false**.
- Per-project override: nullable `projects.allow_self_approval`. `null` means "use the global setting"; `true` or `false` overrides it for that project.
- Effective value = project override if not null, else global value.
- When the effective value is false: the approve endpoint returns 403 if the approver is the user who created the version being approved (generation, edit or section redo). (proposal: counts any author of that version, so edit-then-approve by the same person is also blocked.)
- Always store `self_approved` (true/false) on the approval row and in audit metadata, even while the setting is on.
- Only holders of `settings.manage` can change either level. Every change is audit-logged (who, scope, old value, new value, when).

### 4.5 Authentication
- Email + password, hashed with argon2 (or bcrypt).
- JWT access token (short-lived) plus refresh token (httpOnly cookie).
- Admin creates users and assigns roles (no public sign-up).
- Login rate limiting. Deactivation instead of deletion for users (audit trail must keep actor references valid).

---

## 5. Architecture

### 5.1 Stack
- **Backend:** Python, FastAPI, SQLAlchemy 2.x, Alembic migrations, Pydantic v2
- **Database:** PostgreSQL
- **Frontend:** React (Vite, TypeScript recommended), TanStack Query for server state, React Router
- **LLM:** Google Gemini API via the `google-genai` SDK (free tier for development)
- **Documents:** `python-docx` and `docxtpl` for DOCX, `openpyxl` for the estimate spreadsheet
- **File storage:** S3 API throughout (boto3). **MinIO** in development, **AWS S3** in production. Switching is configuration only (endpoint, bucket, credentials). Metadata in Postgres, bytes outside it.
- **Background work:** start with FastAPI background tasks plus status polling; move to a queue (ARQ or Celery) if generation volume or reliability needs it.
- **Deployment (later):** Docker Compose with postgres, minio, backend, frontend for development. AWS for production (details deferred).

### 5.2 Component sketch
```
React SPA
   |  REST/JSON
FastAPI app
   |-- auth + RBAC dependencies
   |-- routers (projects, steps, references, templates, audit, admin)
   |-- step engine (state machine, dependency check, prompt assembly,
   |                edit and section-regen handling)
   |-- llm layer (Gemini wrapper, structured output, retries)
   |-- documents layer (docx/xlsx rendering)
   |-- audit helper (writes in same DB transaction)
   |-- file storage service (S3 API)
PostgreSQL     MinIO / S3
```

### 5.3 Step engine (the core idea)
One generic engine; the eight steps are **configuration**, not eight code paths.

A step definition contains:
- `key`, `title`, `order`
- `depends_on` (previous step key)
- `extra_inputs_schema` (e.g. team form for estimate, sprint settings for sprint plan; none for others)
- `prompt_template` (system + user parts) and its `prompt_version`
- `output_schema` (Pydantic model; one field per document section; sections must be addressable by path for section redo)
- `default_template_key` (document template)
- `reference_tags` (which reference files apply)

Start with definitions in a Python config module. Move to the database only if admins need to edit them.

### 5.4 Suggested folder structure
```
backend/
  app/
    main.py
    config.py
    db.py
    models/            (SQLAlchemy models)
    schemas/           (Pydantic schemas)
    routers/           (auth, users, projects, steps, references, templates, audit, settings)
    services/
      step_engine.py
      audit.py
      storage.py       (S3 API via boto3)
      documents.py
    llm/
      gemini.py
      prompts/         (one folder per step, versioned files: v1, v2, ...)
    steps/             (step definitions config)
  alembic/
  tests/
  .env
frontend/
  src/
    pages/ components/ api/ hooks/
docker-compose.yml     (postgres, minio, backend, frontend)
```

---

## 6. Data model (Postgres)

Use UUID primary keys and `created_at` timestamps (timezone-aware, UTC).

**Auth and RBAC**
- `users`: id, email (unique), full_name, password_hash, is_active, created_at, last_login_at
- `roles`: id, name, description
- `permissions`: id, code
- `role_permissions`: role_id, permission_id
- `user_roles`: user_id, role_id

**Core**
- `projects`: id, name, client_name, status (active, completed, archived), **allow_self_approval (nullable boolean, per-project override)**, created_by, created_at, completed_at
- `project_inputs`: id, project_id, kind, received_at, received_from, subject, body, created_by, created_at
- `files`: id, storage_key, original_name, mime_type, size_bytes, sha256, extracted_text, uploaded_by, created_at (shared by inputs, references, templates, exports)
- `project_input_files`: input_id, file_id
- `step_versions`: id, project_id, step_key, version_no, status, **source (generated | manual_edit | section_regen)**, content (JSONB, validated against the step's schema), inputs (JSONB, e.g. team details), instructions (text, the change request or section instruction), **section_path (text, nullable, for section_regen)**, based_on_version_id, model_id, **prompt_version (text)**, **assembled_prompt (text, nullable for manual_edit)**, tokens_in, tokens_out, error, template_id, created_by, created_at, generation_started_at, generation_finished_at
- `step_version_dependencies`: step_version_id, depends_on_version_id (which approved versions fed this one)
- `approvals`: id, step_version_id (unique), approved_by, approved_at, comment, self_approved
- `exports`: id, step_version_id, template_id, file_id, format, created_by, created_at

**References and templates**
- `reference_documents`: id, scope (global or project), project_id (nullable), title, file_id, step_tags (text array, `{any}` allowed), is_active, uploaded_by, uploaded_at
- `step_version_references`: step_version_id, reference_document_id
- `document_templates`: id, step_key, name, version, file_id, is_default, is_active, uploaded_by, uploaded_at

**System**
- `settings`: key, value (JSONB), updated_by, updated_at
- `audit_log`: id, occurred_at, actor_id, actor_email (snapshot), action, entity_type, entity_id, project_id (nullable), metadata (JSONB), ip_address, user_agent. Append-only (revoke UPDATE/DELETE for the app database role).

---

## 7. API outline (REST)

**Auth/admin:** `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET/POST /users`, `PATCH /users/{id}`, `GET/POST /roles`, `GET/PUT /settings`

**Projects:** `GET/POST /projects`, `GET /projects/{id}`, `PATCH /projects/{id}/settings` (per-project self-approval override), `POST /projects/{id}/inputs`, `GET /projects/{id}/overview`

**Steps:**
- `GET /projects/{id}/steps` (all steps with derived status)
- `POST /projects/{id}/steps/{key}/generate` (body: step inputs such as team details)
- `GET /projects/{id}/steps/{key}/versions`, `GET /step-versions/{id}`
- `POST /step-versions/{id}/request-changes` (body: instructions; full regeneration)
- `POST /step-versions/{id}/edit` (body: edited content; creates a `manual_edit` version)
- `POST /step-versions/{id}/regenerate-section` (body: `section_path`, instruction; creates a `section_regen` version)
- `POST /step-versions/{id}/approve` (body: comment)
- `POST /projects/{id}/steps/{key}/reopen`
- `GET /step-versions/{id}/prompt` (requires `prompt.view`)
- `GET /step-versions/{id}/download?format=docx|xlsx`

**References/templates:** `GET/POST /references`, `PATCH /references/{id}` (tags, active), `DELETE` (soft), same shape for `/templates`

**Audit:** `GET /audit` (filters: project, actor, action, date range), `GET /projects/{id}/audit`, `GET /audit/export?format=csv|pdf`

All mutating endpoints write an audit entry in the same transaction.

---

## 8. LLM layer

### 8.1 Model configuration
- Model ID lives in config (`GEMINI_MODEL`), never hardcoded in code.
- As of early October 2026, Google's Gemini API docs list these Flash model IDs, among others: `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-3.5-flash-lite`. **Re-check the live list before coding**, since models change quickly. Do not use 2.5 models (old).
- Free-tier limits are shown per project in the Google AI Studio rate-limit console and can change. Third-party sites quoted roughly 15 requests/minute and 1,500/day for 3.5 Flash; that is unverified. Check the console.

### 8.2 Structured output
Each step has a Pydantic output schema. Ask Gemini for JSON matching it (`response_schema` in `google-genai`), validate with Pydantic, retry on validation failure (limited attempts). Section redo uses the sub-schema of the targeted node.

### 8.3 Reliability and traceability
- Retry with exponential backoff and jitter on 429 and transient errors.
- Record model ID, token counts and errors on every step version.
- **Store the full assembled prompt** on every AI-generated version, together with `prompt_version` (the version of the prompt template used). Prompt templates live as versioned files; never edit a released version, add a new one.
- Because stored prompts contain client text and reference content, viewing them needs `prompt.view`, and they are covered by backups and by the same data-handling rules as the intake itself.

### 8.4 Prompt assembly (per step)
1. System instructions (role, tone, output rules)
2. Original client input (clearly delimited as data). Follow-up emails are not included in v1.
3. Approved outputs of earlier steps
4. Applicable reference documents (global plus project, filtered by step tag), size-capped
5. Template section guidance
6. Step-specific user inputs (e.g. team details)
7. For change requests: the previous version plus the instruction text
8. For section redo: the current document, the target path, the instruction, and the sub-schema to return

### 8.5 Safety notes
- **Client emails are untrusted text.** Delimit them and instruct the model to treat them as data only (prompt injection risk).
- **Free-tier data use:** free-tier Gemini requests may be used to improve Google's products. Use dummy data in development. Move to a paid or prepaid key before real client data goes in.
- All arithmetic (estimate totals, weeks, sprint capacity) is computed in Python, never by the model.

---

## 9. Step definitions

### 9.1 Step 1: Scope Analysis
Input: initial intake plus references. Output sections: executive summary, objectives, stakeholders and users, in-scope items, explicitly out-of-scope or assumed items, ambiguities and questions for the client, risks, dependencies, assumptions.

### 9.2 Step 2: Gap Analysis
Input: approved scope analysis plus original intake. Output: list of gaps, each with category (missing requirement, ambiguity, conflict, undefined non-functional requirement, unknown integration, compliance), severity, why it matters, a suggested clarification question, and a suggested default assumption if unanswered. Also a consolidated question list for the client.

### 9.3 Step 3: Feature List
Input: approved gap analysis and scope analysis. Output: modules, each with features; per feature: description, platform or actor (web, mobile, admin), priority (MoSCoW), dependencies, linked assumptions or gaps.

### 9.4 Step 4: Estimate
Input: approved feature list **plus team details entered by the user before generation:**
- Roles and headcount (e.g. 2 backend, 1 frontend, 1 mobile, 1 QA, 1 PM)
- Productive hours per person per week (or allocation %)
- Buffer/contingency %
- Optional: sprint length, QA and PM overhead %

Output: per feature, tasks with hours by role (model proposes). **System calculates:** total hours, hours per role, buffer, calendar weeks given the team. Downloads: DOCX and XLSX (XLSX with live formulas).

Note on editing: after a manual edit or section redo, totals are recomputed by the system, never taken from edited numbers.

### 9.5 Step 5: Statement of Work
Input: approved estimate, feature list, scope analysis. Output: overview, objectives, scope of work, deliverables, out of scope, assumptions, timeline and milestones, team, commercials (placeholders), acceptance criteria, change control, payment terms (placeholders).

### 9.6 Step 6: SRS
Input: approved SOW and feature list. Output (IEEE 29148-style): introduction, overall description, specific requirements (functional by module), external interfaces, non-functional requirements (performance, security, availability, etc.), constraints, appendices.

### 9.7 Step 7: Sprint Plan (required, before FRS)
Input (proposal): approved SRS, feature list and estimate, plus user inputs before generation: sprint length, team capacity per sprint (default taken from the estimate team details, editable), sprint zero or hardening sprint yes/no.
Output: sprints with goals, stories (linked to features), estimates, capacity per sprint, dependencies and release milestones. **System calculates** per-sprint load against capacity and flags overloaded sprints; the model only proposes the allocation.

### 9.8 Step 8: FRS
Input: approved SRS, feature list and sprint plan. Output per feature: description, actors, preconditions, main flow, alternate flows, business rules, field-level validations, error handling, permissions, acceptance criteria, UI notes. Approving this completes the project.

---

## 10. Reference files and templates

### 10.1 Reference files
- Two scopes: **global** (company standards, past SOWs, sample SRS) and **per project** (client brand guide, earlier documents).
- Each file is tagged with the step keys it applies to (`any` allowed). Users can activate or deactivate files without deleting them.
- On upload: store file, extract text (pypdf, python-docx, plain text), save to `files.extracted_text`.
- On generation: include active applicable references in the prompt, with a size cap. Record which were used in `step_version_references`.
- Later, if the library grows: add pgvector retrieval. Not for v1.

### 10.2 Templates
A template does two jobs:
1. Defines the **sections** the AI writes (drives the output schema and prompt guidance).
2. Defines the **look** of the final file: an uploaded `.docx` with Jinja placeholders rendered by `docxtpl`, so branding carries over.

Multiple templates per step with one default. Record the template version used for each export.

---

## 11. Audit trail

### 11.1 What is logged
`user.login`, `user.created`, `user.updated`, `role.changed`, `project.created`, `input.added` (with `received_at` and `recorded_at`), `step.generate_requested`, `step.generated`, `step.generation_failed`, `step.changes_requested`, `step.edited`, `step.section_regenerated` (with `section_path`), `step.approved` (with `self_approved`), `step.reopened`, `document.downloaded`, `prompt.viewed`, `reference.uploaded|activated|deactivated|deleted`, `template.uploaded|activated`, `settings.changed` (global), `project.settings_changed` (per-project override), `audit.exported`.

### 11.2 Requirements
- Written in the **same transaction** as the action. No action without a log line.
- Append-only, enforced at database level.
- Stores an actor email snapshot so history stays readable even if users change.
- Views: per project timeline (when the initial email arrived, who did each step, every edit, when, who approved, when) and a global log with filters (actor, action, project, date).
- **Download:** CSV, plus a readable PDF or DOCX per project. Exports are themselves audited.
- Optional later: hash chain (`prev_hash`, `row_hash`) for tamper evidence.

---

## 12. Frontend screens

- Login
- Projects list (status, current step, created by, dates)
- New project (intake form with attachments)
- **Project workspace:** stepper for the eight steps with statuses; per step: Generate (with the extra-inputs form for steps 4 and 7), output viewer, **inline section editor, per-section "Redo with AI" action**, change-request box, Approve button, version history (showing source of each version), Download; project timeline panel
- Reference library (upload, tag, activate)
- Templates (upload, set default, version)
- Audit trail (project and global, filters, export)
- Admin: users, roles and permissions, settings (global self-approval toggle); project settings (per-project override); prompt viewer (needs `prompt.view`)

Polling for generation status in v1. UI elements are hidden by permission, but the server is the real gate.

---

## 13. Security and quality

- Server-side permission checks on every endpoint; tests for them.
- Argon2 password hashing, refresh token in httpOnly cookie, CORS locked to known origins, login rate limit.
- File uploads: allowed types, size limits, store outside the web root (bucket, private), hash recorded.
- Secrets in environment variables; `.env` never committed.
- Prompt-injection hygiene (section 8.5); never execute anything from client text.
- Stored prompts treated as sensitive data (permission-gated, backed up, covered by the same retention rules as intake).
- Tests: pytest for the step state machine (locking, versions, stale logic, edit and section-regen splicing), permissions, self-approval resolution (global vs project), audit writes, estimate and sprint arithmetic. Light frontend tests later.
- Structured logging; Alembic for every schema change.
- `tsc --noEmit` must pass on every frontend change.
- Backups of Postgres and the file store before real use.

---

## 14. Roadmap

Each phase ends with something runnable.

**Phase 0: Foundations (current)**
- Repo skeleton, `config.py` (pydantic-settings: `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL`, plus S3/MinIO settings when storage starts)
- `llm/gemini.py`: `generate_structured(prompt, schema)` returning a validated Pydantic object, with retry and backoff on 429
- Done when: a script gets a validated structured answer from the configured Gemini model.

**Phase 1: Data, auth, RBAC, audit**
- Postgres, SQLAlchemy models, Alembic initial migration
- Login, JWT, permission dependencies, seed roles and an admin user
- Audit helper used by every write
- Done when: you can log in, a protected endpoint rejects the wrong role, and each action leaves an audit row.

**Phase 2: Projects and intake**
- Create project with initial input and attachments (stored via the S3 API against MinIO), list and view projects
- Done when: a project can be created and the intake is stored immutably with both timestamps.

**Phase 3: Step engine with step 1 only**
- State machine, dependency check, background generation, versions (with `source`), request changes, approve
- Store assembled prompt and `prompt_version` on each generated version
- Minimal React screens for the workspace
- Done when: scope analysis can be generated, revised, approved, and the audit trail shows it all.

**Phase 3b: Editing and section redo**
- Inline edit endpoint and editor, section-path addressing, section regeneration with sub-schema validation, splice logic
- Done when: you can edit a section by hand, redo one line with AI, and version history shows each change with its source.

**Phase 4: References and templates**
- Upload and tagging, prompt injection of references, template upload and docxtpl rendering
- Done when: a generated document uses a reference and a custom template, and the version records which.

**Phase 5: Remaining steps**
- Steps 2 to 8 as config, extra-inputs forms and calculations for the estimate and sprint plan, XLSX export
- Reopen and stale logic, project completion on FRS approval
- Done when: a full project runs end to end.

**Phase 6: Audit views, admin, polish**
- Audit screens and exports, user and role admin, settings (global and per-project self-approval), prompt viewer
- Docker Compose (postgres, minio, backend, frontend), backups, basic hardening
- Done when: a non-developer can run a project and an auditor can reconstruct what happened.

**Later:** AWS deployment, pgvector retrieval, hash-chained audit, queue worker, including follow-up client emails in later steps, notifications.

---

## 15. Decisions log

**Decided**
- Stack: FastAPI, React, PostgreSQL, Gemini API (free tier for development)
- Workflow: eight steps in fixed order, each gated on approval of the previous; Sprint Plan is required and sits before FRS
- Each step: user-initiated, output review, change requests, inline edit and AI section redo before approval, approval, download
- Project completes when FRS is approved
- Full audit trail, viewable and downloadable; login, user management, RBAC
- Reference files and templates supported
- Reopening an approved step marks downstream steps stale; nothing is deleted
- Unapproved versions can be downloaded with a DRAFT marker
- Follow-up client emails are stored but not used in later steps in v1 (maybe a future version)
- Inline editing plus AI redo of a single section or line is in v1
- Self-approval: global setting plus per-project override; allowed for now
- File storage: S3 API; MinIO in development, AWS S3 later
- Hosting: AWS, not a concern now
- Full assembled prompts are stored, with versioned prompt templates
- Model ID configurable; use current Gemini models (3.5 or newer), not 2.5
- Atanu writes the code with step-by-step guidance

**Open (proposals marked above, please confirm or change)**
1. Sprint plan inputs: SRS + feature list + estimate, with sprint length and capacity entered by the user. Right set?
2. Edits only allowed on the latest unapproved version (reopen first to change an approved one). Confirm?
3. Editor style: structured per-section form rather than free-form rich text. Confirm?
4. Section redo addressing by JSON path (section or single line). Confirm that line-level redo is needed in v1, or section-level only at first?
5. Self-approval block when the approver authored any part of the version (generation, edit or section redo). Confirm?
6. Retention period for stored prompts and who may view them (currently `prompt.view` for Lead and Admin).
7. Production hosting details on AWS and who administers it (deferred).

---

## 16. Current status

- Early demo built earlier in the chat (a four-tab Flask app) was **discarded**: wrong model, modules not linked, untested. Do not reuse it.
- Plan updated to v1.1 with the decisions above.
- Phase 0 is assigned to Atanu: set up the backend structure, `config.py`, and `llm/gemini.py` as described above. Nothing written yet as far as this plan knows.
- Next action: Atanu pastes his Phase 0 code for review.
