# ExamSentinel — REST API Contract

> **Status:** Pre-implementation contract
> **Companion to:** `docs/ARCHITECTURE.md`
> **Base URL:** `https://<railway-domain>/api/v1`

This document is the single source of truth for every HTTP endpoint the server exposes. No code lives here; only the contract.

---

## 1. Conventions

### 1.1 Versioning
Every endpoint is mounted under the prefix `/api/v1`. Breaking changes ship as `/api/v2`; `/api/v1` is preserved until all clients have migrated. All paths in this document are written without the prefix for brevity (e.g. `POST /auth/login` means `POST /api/v1/auth/login`).

### 1.2 Content type
All request and response bodies are JSON encoded as UTF-8. Clients must send `Content-Type: application/json` on any request that carries a body. Empty bodies are permitted only on `GET` and `DELETE` requests.

### 1.3 Authentication
The server issues JSON Web Tokens at login. Each token carries the user's numeric `id`, `role` (`student` or `teacher`), an `iat` (issued-at) claim, and an `exp` (expiry) claim set to **twelve hours** after issuance. Tokens are signed with the server's secret key (HMAC-SHA-256). Clients send the token on every protected request as `Authorization: Bearer <token>`. The server validates the signature, expiry, and role on every call. Refresh tokens are not issued; an expired token forces the client back to the login screen.

Passwords are never stored in plain text. The server uses `werkzeug.security.generate_password_hash` to hash passwords on registration and `check_password_hash` to verify them on login. The hash algorithm and salt are stored in the same column.

### 1.4 Roles
Two roles exist: `student` and `teacher`. Each endpoint declares which roles may access it. A request whose token role is not in the allow-list is rejected with `403 forbidden`. A request with no token (or an invalid/expired token) on a protected endpoint is rejected with `401 unauthorized`.

### 1.5 Error envelope
Every non-2xx response has the same JSON shape, regardless of which endpoint produced it:

- **`error.code`** — a stable, machine-readable string in `snake_case`, e.g. `invalid_credentials`, `validation_failed`, `forbidden`, `not_found`, `conflict`, `internal_error`. Clients branch on this field, not on the human message.
- **`error.message`** — a single human-readable sentence safe to surface in the UI.
- **`error.details`** — optional. For validation errors it is an object whose keys are field names and whose values are arrays of human-readable problem strings for that field. For other errors it may carry a small object with contextual hints (e.g. the conflicting resource's id) or be omitted.

Standard status codes used by the envelope:

| Status | When |
|---|---|
| `400 bad_request` | Malformed JSON or missing required header. |
| `401 unauthorized` | Missing, invalid, or expired token. `error.code` = `unauthorized` or `token_expired`. |
| `403 forbidden` | Authenticated but role or ownership check failed. `error.code` = `forbidden`. |
| `404 not_found` | Target resource does not exist or is not visible to the caller. `error.code` = `not_found`. |
| `409 conflict` | Uniqueness or state-machine conflict (e.g. duplicate username, session already submitted). `error.code` = `conflict`. |
| `422 unprocessable_entity` | Body parsed but failed semantic validation. `error.code` = `validation_failed`; `error.details` is populated per field. |
| `500 internal_error` | Unhandled server fault. `error.code` = `internal_error`; `error.details` is omitted in production. |

### 1.6 Pagination
All list endpoints accept two query parameters:

- **`page`** — 1-indexed page number. Default `1`. Values below `1` are rejected with `422`.
- **`page_size`** — number of items per page. Default `20`. Maximum `100`. Values above the max are clamped to `100`; non-positive values are rejected with `422`.

Every paginated response is an object with two keys: an `items` array containing the page contents, and a `pagination` object containing `page`, `page_size`, `total_items`, and `total_pages`. The shape is identical across every list endpoint so clients can share rendering code.

### 1.7 Timestamps
All timestamps are ISO-8601 strings in UTC with a trailing `Z` (e.g. `2026-05-03T08:30:00Z`). The server is the sole authority on time — clients never send "now". Durations are integers in seconds unless explicitly named otherwise.

### 1.8 Identifiers
All primary keys are positive integers. They appear in URL paths as plain integers (e.g. `/exams/42`). Identifiers are never reused after deletion.

### 1.9 Answer-key confidentiality
**The `correct_answer` field of an MCQ question is never serialised in any response whose caller has the `student` role.** This rule applies to every endpoint that returns questions, including session start, session detail, and any exam-preview endpoint. Teachers receive the full question payload including `correct_answer`. The server enforces this in the serialiser, not in the route handler, so it cannot be bypassed by a new endpoint forgetting the rule.

---

## 2. Auth

### `POST /auth/register`
**Roles:** public (no token required).
**Request body in prose.** The caller submits a `username` string (3–32 characters, unique), an `email` string (RFC-5322 format, unique), a `password` string (minimum 8 characters), a `full_name` string, and a `role` discriminator that is exactly one of `student` or `teacher`. When the role is `student`, the body additionally carries a `roll_number` string (unique among students) and a `department_id` integer referencing the department the student belongs to. When the role is `teacher`, the body additionally carries an `employee_code` string (unique among teachers) and a `department_id` integer.
**Response in prose.** On success the response carries the newly created user's `id`, `username`, `email`, `full_name`, `role`, `department_id`, and the role-specific identifier (`roll_number` or `employee_code`), plus `created_at`. No token is issued at registration; the client must call `POST /auth/login` next.
**Success status:** `201 created`.
**Validation rules.** Username and email are trimmed and lowercased before uniqueness checks. Password is hashed with werkzeug before storage. A duplicate username or email returns `409 conflict` with `error.code = conflict` and `error.details.field` indicating which one collided. Missing or malformed fields return `422 validation_failed` with per-field details. The role-specific block (`roll_number` or `employee_code`) is required if and only if it matches the chosen role; sending the wrong block returns `422`.

### `POST /auth/login`
**Roles:** public.
**Request body in prose.** The caller submits a `username` string (or `email` — the server accepts either in the same field) and a `password` string.
**Response in prose.** On success the response carries an `access_token` string (the JWT), a `token_type` string fixed to `bearer`, an `expires_in` integer fixed to `43200` (twelve hours in seconds), and a `user` object containing the user's `id`, `username`, `email`, `full_name`, `role`, `department_id`, and the role-specific identifier. The `user` object lets the client populate its dashboard immediately without a second round-trip.
**Success status:** `200 ok`.
**Validation rules.** Invalid credentials return `401 unauthorized` with `error.code = invalid_credentials` and a generic message that does not disclose which of the username or password was wrong. The server updates the user's `last_login` timestamp on success.

### `GET /auth/me`
**Roles:** student, teacher.
**Request body in prose.** None. The token in the `Authorization` header identifies the caller.
**Response in prose.** Returns the same `user` object shape as `POST /auth/login`. Clients call this on app start (when a stored token exists) to refresh role and profile state without forcing a re-login.
**Success status:** `200 ok`.
**Validation rules.** A missing or expired token returns `401`. There is no body to validate.

---

## 3. Departments and Users

### `GET /departments`
**Roles:** student, teacher.
**Request body in prose.** None. Accepts standard pagination query parameters.
**Response in prose.** A paginated list of departments. Each item carries the department's `id`, `name` (e.g. `Computer Science`), `code` (e.g. `CS`), and `created_at`. Departments are read-only via the API in v1; they are seeded during deployment.
**Success status:** `200 ok`.
**Validation rules.** Pagination parameters validated per §1.6.

### `GET /users/students`
**Roles:** teacher only.
**Request body in prose.** None. Accepts pagination and the following optional filter query parameters: `department_id` (integer, restricts to one department), `course_id` (integer, restricts to students enrolled in that course with status `active`), `q` (case-insensitive substring match against `full_name`, `username`, `email`, and `roll_number`).
**Response in prose.** A paginated list of student summaries. Each item carries the student's `id`, `username`, `email`, `full_name`, `roll_number`, `department_id`, and `department_name`.
**Success status:** `200 ok`.
**Validation rules.** A `student` caller receives `403 forbidden`. Unknown `department_id` or `course_id` returns an empty page (not 404). `q` is trimmed; an empty `q` is treated as omitted.

---

## 4. Courses and Enrollments

### `POST /courses`
**Roles:** teacher only.
**Request body in prose.** Carries a `title` string (1–120 chars), a `code` string (e.g. `CS201`, unique across all courses, 2–20 chars, alphanumeric), and an optional `description` string (up to 2000 chars).
**Response in prose.** The created course: `id`, `title`, `code`, `description`, `teacher_id` (the caller), `teacher_name`, `created_at`, and an `enrollment_count` integer initialised to zero.
**Success status:** `201 created`.
**Validation rules.** Duplicate `code` returns `409 conflict`. The caller is automatically set as the owning teacher; the body cannot override `teacher_id`.

### `GET /courses/{course_id}`
**Roles:** student, teacher.
**Request body in prose.** None.
**Response in prose.** The full course object as in the create response, plus an `exam_count` integer.
**Success status:** `200 ok`.
**Validation rules.** A teacher who does not own the course receives `403`. A student not enrolled in the course receives `403`. A non-existent id returns `404`.

### `PATCH /courses/{course_id}`
**Roles:** teacher only (must own the course).
**Request body in prose.** Carries any subset of `title`, `code`, `description`, with the same validation rules as create. At least one field must be present.
**Response in prose.** The updated course object.
**Success status:** `200 ok`.
**Validation rules.** Empty body returns `422`. Code uniqueness is re-checked on change.

### `DELETE /courses/{course_id}`
**Roles:** teacher only (must own the course).
**Request body in prose.** None.
**Response in prose.** Empty body.
**Success status:** `204 no_content`.
**Validation rules.** Deletion is rejected with `409 conflict` if any exam in the course has at least one `submitted` or `reviewed` session — historical academic records must be preserved. To remove such a course, the teacher must first archive its exams (out of scope for v1).

### `GET /courses/me`
**Roles:** student, teacher.
**Request body in prose.** None. Accepts pagination.
**Response in prose.** A paginated list of courses visible to the caller. For a teacher, this is the courses they own. For a student, this is the courses where an active enrollment exists. Each item is the course summary shape (id, title, code, description, teacher_id, teacher_name, exam_count, plus, for students, an `active_exam_count` integer indicating how many exams are currently within their `start_window`/`end_window` and have `is_active = true`).
**Success status:** `200 ok`.

### `POST /courses/{course_id}/enrollments`
**Roles:** teacher only (must own the course).
**Request body in prose.** Carries a `student_email` string identifying the student to enrol. The server resolves the email to a student account; the email-based form keeps the teacher's workflow simple and avoids forcing them to look up student ids.
**Response in prose.** The created enrollment: `id`, `course_id`, `student_id`, `student_full_name`, `student_email`, `student_roll_number`, `enrolled_at`, and `status` (initially `active`).
**Success status:** `201 created`.
**Validation rules.** An unknown email returns `404 not_found` with `error.code = not_found` and `error.details.field = student_email`. An email that resolves to a teacher account returns `422 validation_failed`. An already-active enrollment for that student in that course returns `409 conflict`. A previously dropped enrollment is re-activated rather than duplicated; the response status is still `201` but the same `id` is returned.

### `DELETE /courses/{course_id}/enrollments/{enrollment_id}`
**Roles:** teacher only (must own the course).
**Request body in prose.** None.
**Response in prose.** Empty body.
**Success status:** `204 no_content`.
**Validation rules.** This sets `status = dropped`; the row is preserved for audit. A drop is rejected with `409 conflict` if the student has any `in_progress` session in the course.

### `GET /courses/{course_id}/enrollments`
**Roles:** teacher only (must own the course).
**Request body in prose.** None. Accepts pagination and an optional `status` filter (`active` or `dropped`; default `active`).
**Response in prose.** A paginated list of enrollments with the same item shape as the create response.
**Success status:** `200 ok`.

---

## 5. Exams and Questions

### `POST /courses/{course_id}/exams`
**Roles:** teacher only (must own the course).
**Request body in prose.** Carries a `title` string (1–200 chars), an optional `description` string (up to 4000 chars), a `duration_minutes` integer (1–600), a `start_window` ISO-8601 timestamp, an `end_window` ISO-8601 timestamp (must be strictly after `start_window`), and a `questions` array. Each entry in `questions` carries a `question_text` string (1–4000 chars), a `question_type` string that is exactly one of `mcq` or `short_answer`, a `marks` integer (1–100), an `order_index` integer (used to sort within the exam; must be unique within the array), and — only when `question_type` is `mcq` — an `options` array of 2–6 non-empty strings and a `correct_answer` string that must equal one of the `options`. For `short_answer` questions the `options` and `correct_answer` fields must be omitted or null. The exam is created with `is_active = false` so the teacher can review before exposing it to students.
**Response in prose.** The created exam: `id`, `course_id`, `title`, `description`, `duration_minutes`, `start_window`, `end_window`, `is_active`, `created_at`, and a nested `questions` array. Because the caller is a teacher, each question carries its `correct_answer`. Each question also carries `id`, `question_text`, `question_type`, `options`, `marks`, and `order_index`.
**Success status:** `201 created`.
**Validation rules.** All field-level checks above produce `422 validation_failed` with per-field details. An `mcq` whose `correct_answer` is not in `options` is a validation failure. Duplicate `order_index` values are a validation failure. An empty `questions` array is a validation failure.

### `GET /exams/{exam_id}`
**Roles:** student, teacher.
**Request body in prose.** None.
**Response in prose.** For a teacher who owns the exam's course: the full exam object including `correct_answer` for each MCQ. For a student enrolled in the exam's course: the exam summary (no questions array, only metadata and `question_count`) — the question content is delivered only via `POST /sessions` to prevent leak before the exam starts.
**Success status:** `200 ok`.
**Validation rules.** Teachers who do not own the course and students not enrolled receive `403`.

### `PATCH /exams/{exam_id}`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** Carries any subset of `title`, `description`, `duration_minutes`, `start_window`, `end_window`. Question editing is a separate operation. At least one field must be present.
**Response in prose.** The updated exam object.
**Success status:** `200 ok`.
**Validation rules.** Editing is rejected with `409 conflict` if any session for this exam has reached `in_progress` or beyond — a live exam's parameters cannot be changed mid-flight.

### `DELETE /exams/{exam_id}`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** Empty body.
**Success status:** `204 no_content`.
**Validation rules.** Rejected with `409 conflict` if any `submitted` or `reviewed` session exists.

### `PUT /exams/{exam_id}/questions`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** Carries a `questions` array with the same shape and rules as the create endpoint. This is a full replacement of the exam's question set, performed atomically.
**Response in prose.** The updated exam object with its new questions array.
**Success status:** `200 ok`.
**Validation rules.** Rejected with `409 conflict` if any session for this exam has progressed beyond `pre_check`.

### `POST /exams/{exam_id}/activate`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** The exam object with `is_active = true`.
**Success status:** `200 ok`.
**Validation rules.** Rejected with `422 validation_failed` if the exam has zero questions or if `end_window` is already in the past.

### `POST /exams/{exam_id}/deactivate`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** The exam object with `is_active = false`.
**Success status:** `200 ok`.
**Validation rules.** Allowed at any time. In-progress sessions are not aborted; they continue to completion. New sessions can no longer be started.

### `GET /exams/active`
**Roles:** student only.
**Request body in prose.** None. Accepts pagination.
**Response in prose.** A paginated list of exam summaries that are simultaneously: (a) belong to a course in which the caller has an `active` enrollment, (b) have `is_active = true`, (c) the current server time falls within `[start_window, end_window]`, and (d) the caller has no `submitted` or `reviewed` session for them yet (so completed exams are filtered out). Each item carries `id`, `title`, `description`, `duration_minutes`, `start_window`, `end_window`, `course_id`, `course_title`, `course_code`, and `question_count`. Question content is intentionally absent.
**Success status:** `200 ok`.

---

## 6. Sessions and Answers

### `POST /sessions`
**Roles:** student only.
**Request body in prose.** Carries an `exam_id` integer.
**Response in prose.** The created session: `id`, `exam_id`, `student_id`, `status` (always `pre_check` at this point), `started_at` (null at this point), a `deadline_at` ISO-8601 timestamp the server will enforce once the session transitions to `in_progress` (computed but not yet started; reported here so the client can show it on the pre-check screen), `time_remaining_seconds` (equal to `duration_minutes * 60` since the session has not started), and a `questions` array. Each question carries `id`, `question_text`, `question_type`, `options` (for MCQs), `marks`, and `order_index`. **The `correct_answer` field is omitted for the student-role caller per §1.9.** The session id is what the client uses for every subsequent call (answer save, incident, submit).
**Success status:** `201 created`.
**Validation rules.** The exam must be active and within its window, and the student must be enrolled in its course; otherwise `403 forbidden` with a precise `error.code` (`exam_not_active`, `exam_window_closed`, or `not_enrolled`). If the student already has a `pre_check` or `in_progress` session for this exam, that session is returned instead of creating a new one (idempotent restart). If the student has a terminal session (`submitted`, `reviewed`, `aborted_vm`, `aborted_stealth_vm`) and retakes are not allowed, `409 conflict` with `error.code = already_attempted`.

### `PATCH /sessions/{session_id}`
**Roles:** student only (must own the session).
**Request body in prose.** Carries a `status` string that is exactly one of `in_progress`, `aborted_vm`, `aborted_stealth_vm`, or `submitted`. The state machine is enforced server-side: only `pre_check → in_progress`, `pre_check → aborted_vm`, `pre_check → aborted_stealth_vm`, and `in_progress → submitted` are accepted. Submitting via this endpoint is equivalent to `POST /sessions/{id}/submit` (see below) — both are accepted; the `submit` form is preferred because it returns the score.
**Response in prose.** The updated session object: `id`, `exam_id`, `student_id`, `status`, `started_at`, `submitted_at`, `deadline_at`, `time_remaining_seconds`, and (for `submitted`) `score`.
**Success status:** `200 ok`.
**Validation rules.** Disallowed transitions return `409 conflict` with `error.code = invalid_state_transition`. The transition to `in_progress` sets `started_at` to the server's current time and computes `deadline_at = started_at + duration_minutes * 60`.

### `PUT /sessions/{session_id}/answers/{question_id}`
**Roles:** student only (must own the session).
**Request body in prose.** Carries an `answer_text` string. For MCQs this must equal one of the question's `options` strings; for short-answer questions it is free text up to 8000 characters. The endpoint is an upsert keyed on the `(session_id, question_id)` pair — the latest write wins; previous values are overwritten in place, not versioned.
**Response in prose.** The saved answer: `id`, `session_id`, `question_id`, `answer_text`, and `saved_at`. The `is_correct` and `marks_awarded` fields are not returned during the live phase even if the question is an MCQ — students must not learn correctness mid-exam.
**Success status:** `200 ok` (upsert returns the same status whether it created or updated).
**Validation rules.** The session must be `in_progress` and `deadline_at` must be in the future; otherwise `409 conflict` with `error.code = session_not_active` or `session_expired`. The question must belong to the session's exam; otherwise `422`. An MCQ answer that is not one of the `options` strings is a `422` validation failure with `error.details.answer_text`.

### `POST /sessions/{session_id}/submit`
**Roles:** student only (must own the session).
**Request body in prose.** None. Submission is intentionally body-less; all answers are already on the server via the auto-save endpoint.
**Response in prose.** The finalised session: `id`, `exam_id`, `status` (`submitted`), `started_at`, `submitted_at`, `score` (sum of `marks` for MCQs whose `answer_text` matches `correct_answer`, leaving short-answer questions ungraded), `total_marks` (sum of `marks` across all questions), `mcq_marks_awarded`, `mcq_marks_possible`, `pending_manual_marks` (sum of `marks` for ungraded short-answer questions). The score may rise after teacher review; the client labels it provisional when `pending_manual_marks > 0`.
**Success status:** `200 ok`.
**Validation rules.** The session must be `in_progress`; otherwise `409 conflict`. Submitting after `deadline_at` is allowed but recorded — the auto-grader runs the same way; the server may attach a synthetic `IncidentLog` of type `lockdown_violation` (subtype `late_submit`) for the teacher's awareness.

### `GET /sessions/{session_id}/time`
**Roles:** student only (must own the session).
**Request body in prose.** None.
**Response in prose.** A small object with `server_time` (ISO-8601, the server's current clock), `deadline_at` (ISO-8601), `time_remaining_seconds` (integer, never negative — clamped to zero when the deadline has passed), and `expired` (boolean). The client uses this to render its countdown without trusting the local OS clock.
**Success status:** `200 ok`.
**Validation rules.** The session must be `in_progress`; for any other state the response carries `time_remaining_seconds = 0` and `expired = true`.

### `GET /sessions/{session_id}/result`
**Roles:** student (must own the session) or teacher (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** The student-facing result object: `id`, `exam_id`, `exam_title`, `status`, `started_at`, `submitted_at`, `score`, `total_marks`, `mcq_marks_awarded`, `mcq_marks_possible`, `pending_manual_marks`, and a `breakdown` array. Each entry in `breakdown` carries `question_id`, `question_text`, `question_type`, `marks`, the student's `answer_text`, `is_correct` (only for MCQs), and `marks_awarded` (null for ungraded short-answer questions). **For a `student` caller, `correct_answer` is omitted from the breakdown to preserve the answer key.** For a `teacher` caller, `correct_answer` is included.
**Success status:** `200 ok`.
**Validation rules.** Available only after the session reaches `submitted` or `reviewed`; otherwise `409 conflict` with `error.code = session_not_finalised`.

---

## 7. Incident Logs

**Implementation note.** The current backend and VM integration use `POST /sessions/{session_id}/incident` for one event and `POST /sessions/{session_id}/incidents` for bulk ingestion. Incident payloads use `type`, `severity`, optional `description`, and optional forensic fields `cpu_thermal_value`, `timing_latency_ms`, and `evidence_path`; the VM guide's `VM_DETECTED` and `STEALTH_VM_DETECTED` values are the canonical VM incident types.

### `POST /sessions/{session_id}/incidents`
**Roles:** student only (must own the session).
**Request body in prose.** Carries an `incident_type` string that is exactly one of `vm_detected`, `stealth_vm_detected`, `focus_loss`, `blacklist_process_killed`, `clipboard_scrubbed`, `lockdown_violation`, `timing_anomaly`, `thermal_anomaly`. Carries a `severity` string that is exactly one of `info`, `warning`, `critical`. Carries a `client_timestamp` ISO-8601 string indicating when the event was observed on the client (the server records its own receive timestamp separately so clock skew is auditable). Carries a `detail` object whose contents are free-form but typed by `incident_type`: for `focus_loss` it carries the foreground window title and process name; for `blacklist_process_killed` it carries the process name and pid; for `clipboard_scrubbed` it carries a hash and length of the scrubbed content (never the content itself); for `lockdown_violation` it carries the violation kind (e.g. `keyboard_combo`) and a key sequence; for `vm_detected` and `stealth_vm_detected` it carries the list of detector names that triggered. For stealth-VM evidence the `detail` may additionally carry `timing_samples` (an array of float microsecond deltas from RDTSC probes) and `thermal_samples` (an array of float Celsius readings from the thermal sensors, or an empty array indicating "no sensor present", which is itself evidence of a virtualised environment). Both fields are optional and only populated for VM-related incidents.
**Response in prose.** The created incident: `id`, `session_id`, `incident_type`, `severity`, `client_timestamp`, `server_timestamp`, and `detail`.
**Success status:** `201 created`.
**Validation rules.** The session must exist and belong to the caller; otherwise `403`. The session may be in any non-terminal state — incidents are accepted during `pre_check`, `in_progress`, and even briefly after `submitted` to allow the post-phase flush. After `reviewed` the endpoint rejects with `409 conflict`. The `detail` object is stored as JSONB; the server validates the `incident_type`-specific shape and returns `422 validation_failed` with per-field details on mismatch.

### `POST /sessions/{session_id}/incidents/bulk`
**Roles:** student only (must own the session).
**Request body in prose.** Carries an `incidents` array of up to 500 entries, each shaped exactly like the single-incident body above. Used by the client to flush its local queue at submission time.
**Response in prose.** A `created` array of the saved incident objects in the same order as submitted, plus a `count` integer.
**Success status:** `201 created`.
**Validation rules.** The whole batch is validated before any insert; if any entry fails validation the entire batch is rejected with `422` and `error.details.incidents` carrying an array indexed by position. Bulk inserts above 500 entries return `422`.

---

## 8. Teacher Reporting

**Implementation note.** The current backend mounts teacher reporting under `/teacher`: sessions list at `GET /teacher/exams/{exam_id}/sessions`, detail at `GET /teacher/sessions/{session_id}/detail`, manual grading at `POST /teacher/sessions/{session_id}/grade`, and analytics at `GET /teacher/exams/{exam_id}/analytics`.

### `GET /exams/{exam_id}/sessions`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None. Accepts pagination and an optional `status` filter (any of the lifecycle states from §2 of the architecture document; multiple values comma-separated, e.g. `submitted,reviewed`).
**Response in prose.** A paginated list of session summaries. Each item carries `id`, `student_id`, `student_full_name`, `student_roll_number`, `status`, `started_at`, `submitted_at`, `score`, `total_marks`, `pending_manual_marks`, and `incident_count` (total number of incidents on the session, regardless of severity), and `critical_incident_count` (incidents with `severity = critical`).
**Success status:** `200 ok`.

### `GET /sessions/{session_id}/full`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** The complete teacher-review view of a session, in a single payload to minimise round-trips. Carries the session metadata (id, status, started_at, submitted_at, score, totals), the `student` profile, the `exam` summary, an `answers` array (each entry: `question_id`, `question_text`, `question_type`, `options`, `correct_answer` (teacher-visible), `marks`, the student's `answer_text`, `is_correct`, `marks_awarded`), and an `incidents` array sorted by `server_timestamp` ascending. Each incident entry carries `id`, `incident_type`, `severity`, `client_timestamp`, `server_timestamp`, and `detail`.
**Success status:** `200 ok`.
**Validation rules.** Available for any non-`pre_check` session; for `pre_check` sessions the endpoint returns `409 conflict` since there is nothing meaningful to review yet.

### `PATCH /sessions/{session_id}/answers/{question_id}/grade`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** Carries a `marks_awarded` number (0 ≤ value ≤ the question's `marks`, may be a half-integer like 1.5) and an optional `feedback` string up to 2000 characters surfaced to the student in the result view.
**Response in prose.** The updated answer: `id`, `session_id`, `question_id`, `answer_text`, `marks_awarded`, `feedback`, `graded_at`, `graded_by_teacher_id`.
**Success status:** `200 ok`.
**Validation rules.** Only short-answer questions accept manual grading; attempts to grade an MCQ return `422 validation_failed` with `error.code = validation_failed` and `error.details.question_type`. `marks_awarded` outside `[0, question.marks]` returns `422`. Grading is only allowed when the session is `submitted` or `reviewed`; otherwise `409 conflict`. Grading any answer does not by itself transition the session to `reviewed`; the teacher does so explicitly via `PATCH /sessions/{session_id}` with `status = reviewed`, which the server accepts only when every short-answer question has a non-null `marks_awarded`.

### `PATCH /sessions/{session_id}/review`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None. This is a dedicated endpoint (rather than reusing the generic `PATCH /sessions/{id}`) because the transition is a teacher action, distinct from student-driven state changes.
**Response in prose.** The session object with `status = reviewed` and the recomputed final `score` (MCQ marks plus all manually awarded marks).
**Success status:** `200 ok`.
**Validation rules.** Rejected with `409 conflict` if any short-answer question still has null `marks_awarded`, with `error.details.ungraded_question_ids` listing them.

### `GET /exams/{exam_id}/analytics`
**Roles:** teacher only (must own the exam's course).
**Request body in prose.** None.
**Response in prose.** A summary object intended for a single dashboard panel: `exam_id`, `exam_title`, `total_sessions`, counts by status (`pre_check`, `in_progress`, `submitted`, `reviewed`, `aborted_vm`, `aborted_stealth_vm`), `average_score` (across `submitted` and `reviewed` only; null when zero qualifying sessions), `median_score`, `highest_score`, `lowest_score`, `score_distribution` (an array of `{ bucket_start, bucket_end, count }` entries forming ten equal-width buckets across `[0, total_marks]`), `average_duration_seconds` (mean of `submitted_at - started_at` across finalised sessions), `incident_summary` (an object whose keys are the eight `incident_type` values and whose values are integer counts across all sessions of this exam), and `flagged_session_count` (sessions with at least one `critical` severity incident). All numeric statistics are computed server-side; the client renders without further calculation.
**Success status:** `200 ok`.

---

## 9. Endpoint Summary Index

| Method | Path | Roles | Purpose |
|---|---|---|---|
| POST | `/auth/register` | public | Create account |
| POST | `/auth/login` | public | Issue JWT |
| GET | `/auth/me` | student, teacher | Refresh profile |
| GET | `/departments` | student, teacher | List departments |
| GET | `/users/students` | teacher | List/filter students |
| POST | `/courses` | teacher | Create course |
| GET | `/courses/{id}` | student, teacher | Get course |
| PATCH | `/courses/{id}` | teacher | Update course |
| DELETE | `/courses/{id}` | teacher | Delete course |
| GET | `/courses/me` | student, teacher | List own courses |
| POST | `/courses/{id}/enrollments` | teacher | Enrol student by email |
| DELETE | `/courses/{id}/enrollments/{eid}` | teacher | Drop enrollment |
| GET | `/courses/{id}/enrollments` | teacher | List enrollments |
| POST | `/courses/{id}/exams` | teacher | Create exam with questions |
| GET | `/exams/{id}` | student, teacher | Get exam |
| PATCH | `/exams/{id}` | teacher | Update exam metadata |
| DELETE | `/exams/{id}` | teacher | Delete exam |
| PUT | `/exams/{id}/questions` | teacher | Replace question set |
| POST | `/exams/{id}/activate` | teacher | Activate exam |
| POST | `/exams/{id}/deactivate` | teacher | Deactivate exam |
| GET | `/exams/active` | student | List active exams for caller |
| POST | `/sessions` | student | Start session, get questions |
| PATCH | `/sessions/{id}` | student | State transition |
| PUT | `/sessions/{id}/answers/{qid}` | student | Upsert answer |
| POST | `/sessions/{id}/submit` | student | Submit and auto-grade |
| GET | `/sessions/{id}/time` | student | Server-authoritative timer |
| GET | `/sessions/{id}/result` | student, teacher | Result view |
| POST | `/sessions/{id}/incident` | student | Ingest one incident |
| POST | `/sessions/{id}/incidents` | student | Flush incident queue |
| GET | `/teacher/exams/{id}/sessions` | teacher | Sessions for an exam |
| GET | `/teacher/sessions/{id}/detail` | teacher | Full review payload |
| POST | `/teacher/sessions/{id}/grade` | teacher | Manually grade text answer |
| GET | `/teacher/exams/{id}/analytics` | teacher | Exam analytics summary |
