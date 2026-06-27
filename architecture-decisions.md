# DollarCloud: Architectural Decisions

*Decision log — updated through Phase 2 (Drive scope revision)*

---

## Project Goal

Build **DollarCloud**, a web-based, mobile-aware double-entry accounting application similar to GnuCash. The app must be accessible from any device (desktop, tablet, phone) and must store user data in user-controlled cloud storage, not on the application host.

---

## Decision 1: User-Owned Data Storage

**Decision:** User financial data is stored in the user's own Google Drive (or compatible service), not on the application server.

**Rationale:** Gives users full ownership and control over their data. The application server acts as a thin coordinator, not a data custodian. This simplifies security obligations for the host and builds user trust.

**Implication:** The backend is largely stateless with respect to financial data. It brokers authentication and serves the frontend but never persists transaction records.

---

## Decision 2: Storage Format — SQLite File on Google Drive

**Decision:** User data is stored as a single SQLite file on the user's Google Drive.

**Rationale:** SQLite is a portable, self-contained format well suited to personal and small-business accounting. A single file is conceptually simple for users to understand, back up, and own.

**Known constraint:** Google Drive (and other consumer cloud storage services) do not support concurrent random-access writes. Every session must download the file, work on it, then upload it back. For typical personal finance file sizes (well under 10 MB) this is acceptable.

**Conflict handling:** Optimistic locking will be used. If a user attempts to save and a newer version of the file exists on Drive, they will be warned and asked to reconcile. This is sufficient for the household and small-business use case.

**OAuth scope:** Drive access uses the `drive.file` scope. Full Drive access is not requested.

`drive.file` limits the app to files it created or files the user explicitly opens through a Google Drive picker. It does not grant access to the rest of the user's Drive.

`drive.appdata` was considered and rejected. That scope stores the file in a hidden application folder the user cannot see or navigate to in the Drive UI. It cannot be easily copied, moved, or deleted without going through the app or a buried Drive settings page. That behavior directly contradicts the project's stated goal of giving users genuine ownership and control over their own data.

With `drive.file`, the user chooses a folder during first-run setup. The app creates `dollarcloud.db` in that folder. The file is fully visible in the user's Drive: they can see it, copy it, back it up, move it, or delete it at any time without any involvement from the app.

**Known edge case:** If the user moves or renames the file outside the app, the app will lose track of it. Recovery requires re-running the folder picker to re-link the file. This is a better problem to have than users being unable to access or manage their own data.

**Future upgrade path:** If true concurrent multi-user access is needed later, migrating to a user-hosted Supabase (PostgreSQL) instance is the cleanest path that preserves the user-ownership philosophy.

---

## Decision 3: Backend Stack

**Decision:** Python with FastAPI, hosted on Render.com.

**Rationale:** Python is the developer's preferred language. FastAPI was chosen over Flask specifically for its native async/await support, which is important for OAuth flows and Google Drive operations. A prior Flask project required significant workarounds for async behavior; FastAPI eliminates that class of problem. Render.com was chosen because it supports ASGI frameworks like FastAPI natively, deploys directly from GitHub with automatic redeploys on every push, and has a free tier suitable for development.

**PythonAnywhere was attempted and abandoned.** PythonAnywhere's standard hosting uses WSGI, which is incompatible with ASGI frameworks like FastAPI. Their ASGI support is an experimental beta with significant limitations and no standard web UI. No workaround (a2wsgi, asgiref, uvicorn WSGI middleware) produced a working deployment.

**Design principle:** Keep the backend thin and stateless so that migrating to a different host later is straightforward.

---

## Decision 4: Frontend

**Decision:** A single-page application in vanilla JavaScript or a lightweight framework (Vue is a candidate), served as static files from Render.com or a CDN.

**Rationale:** Keeps the stack simple and consistent with a lean backend. Mobile-aware responsive design is a first-class requirement.

---

## Decision 5: File Format — Custom Schema, Not GnuCash

**Decision:** Define a purpose-built SQLite schema rather than adopting the GnuCash file format.

**Rationale:** The GnuCash schema carries legacy decisions from a desktop application built in the 1990s. A clean schema designed for this app is more maintainable and allows the project to evolve without inherited constraints.

**GnuCash compatibility:** A separate import/export utility will be built to allow users to migrate from GnuCash. This is a utility, not a core dependency.

---

## Decision 6: Core Database Schema

The schema is modeled on the logical structure of double-entry bookkeeping, stripped of GnuCash-specific legacy.

| Table | Purpose |
|---|---|
| `entities` | The user or organization owning the books |
| `accounts` | Chart of accounts; includes account type and parent for hierarchy |
| `transactions` | Transaction header: date, description, memo |
| `splits` | Double-entry lines: transaction, account, amount, reconciliation status |
| `commodities` | Currencies and securities (supports investment tracking later) |

---

## Decision 7: Development Philosophy and Sequence

**Philosophy:** Build in small, independently testable modules. Each phase must be working and validated before the next begins. This keeps bugs easy to isolate and avoids compounding unknowns.

**Decided sequence:**

1. **Bare FastAPI scaffold** ✅ — A minimal FastAPI app running on Render.com with a single test endpoint and no authentication. Validates the hosting setup and project structure. GitHub repository established at `StephenMNolan/gnucash-web` with automatic deploys to Render on every push.

2. **Google OAuth plus Drive file I/O** — Complete the OAuth flow end to end, then prove that the app can read and write a file on the user's Google Drive. This is the highest-risk unknown in the project and must be resolved before the schema is finalized. No local username/password system will be built; Google OAuth is the foundation from the start.

3. **Schema design** — Finalize the database schema on paper first, stress-testing it against real scenarios (multi-split transactions, reconciliation states, opening balances) before writing any DDL.

4. **SQLite CRUD on Drive** — Implement create, read, update, and delete operations against the real schema, with the SQLite file stored on Google Drive.

5. **Entities** — Add maintenance tools for the entities table.

6. **Accounts** — Add maintenance tools for the chart of accounts.

7. **Transactions and splits** — Add maintenance tools for transaction entry and the double-entry split lines.

8. **Commodities** — Add currencies and securities support.

**Note on authentication:** A local username/password system was considered for an early phase but rejected. It would create code that does not survive into production. An unauthenticated stub in phase 1 followed by Google OAuth in phase 2 is the more direct path.

---

## Deferred Decisions

- Specific JavaScript framework for the frontend (vanilla JS vs. Vue vs. other)
- Authentication provider beyond Google (Microsoft, Apple, etc.)
- Offline / progressive web app capabilities
- Reporting and export formats
- Multi-currency and investment account support timeline
