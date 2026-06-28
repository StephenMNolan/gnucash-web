# DollarCloud: Architectural Decisions

*Decision log — updated through Phase 3 completion*

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

## Decision 6: Core Database Schema — Dual-Layer Architecture

### Design Philosophy: "Hood Up vs Driver's Seat"

The schema maintains strict double-entry accounting integrity underneath while providing an intuitive personal finance interface on top — like viewing a car from under the hood versus from the driver's seat.

**Under the Hood (Accounting Engine View):**
- Proper double-entry accounting with debits and credits that must balance
- Complete chart of accounts including equity accounts
- Formal financial statements (Balance Sheet, Income Statement, Cash Flow)
- Account types, contra-accounts, retained earnings

**Driver's Seat (Personal Finance View):**
- Intuitive language ("payees" not "vendors", "net worth" not "equity")
- Task-focused workflows ("Add paycheck", "Reconcile checking", "Where did my money go?")
- Institution-centric organization ("Show all Fidelity accounts")

### The Critical Architectural Insight: Financial Account ≠ Accounting Account

**This is the most important design decision in the schema.**

A **financial account** is a real-world account at an institution:
- "Chase Checking #1234" — has an account number, receives statements, is reconciled against bank records
- "Fidelity Brokerage #5678" — holds securities, receives trade confirmations

An **accounting account** is a category in the chart of accounts:
- "Assets:Current Assets:Checking" — a conceptual bucket for double-entry bookkeeping
- "Assets:Investments:Stocks" — no statements, no reconciliation, part of the balance sheet

**Why this matters:** One Fidelity brokerage account (#123456789) might hold stocks, bonds, and cash. These map to different accounting accounts (Assets:Investments:Stocks, Assets:Investments:Bonds, Assets:Current Assets:Cash), but they all belong to one financial account. GnuCash forces you to create one accounting account per institution account, losing proper categorization. DollarCloud separates them completely.

Similarly, Chase can be both an **institution** (holds your checking account) and a **payee** (you pay your Chase credit card bill). These are different roles served by different tables. The overlap is intentional and correct.

### How the Layers Connect

```
User enters: "Paid $50 at HEB from Chase Checking"

Financial layer records:
  Financial Account: Chase Checking #1234
  Payee: HEB
  Amount: $50

Accounting layer records:
  Debit:  Expenses:Groceries  $50
  Credit: Assets:Checking     $50

Both views are ONE transaction, different perspectives.
```

The bridge between layers is the **split**: each split references both an accounting account (what/why) and a financial account (where). Both references are NOT NULL — every dollar in the system is always traceable to both.

### Table Summary

| Table | Layer | Purpose |
|---|---|---|
| `entity` | System | Single-row file header: owner name, base currency, period metadata, UI preferences |
| `commodities` | Support | Currencies and securities; referenced by FK wherever a currency or security is needed |
| `institutions` | Financial | Banks, brokerages, credit unions |
| `financial_accounts` | Financial | Real-world accounts at institutions |
| `accounts` | Accounting | Chart of accounts; hierarchical double-entry categories |
| `payees` | Support | Merchants, employers, counterparties |
| `transactions` | Transaction | Header record: date, payee, narrative |
| `splits` | Transaction | Double-entry legs; links accounting account + financial account |

**Deferred tables (design unblocked, implementation later):**
- `prices` — historical price data per commodity per date
- `fixed_income_instruments` — fixed income sub-ledger (CDs, Treasuries, coupon tracking)
- `investment_positions` — investment sub-ledger (shares, cost basis, lots)
- `assets` — fixed asset sub-ledger (plant, property, equipment, inventory)

---

## Decision 7: One File Per Period — Annual Close Architecture

**Decision:** One SQLite file covers one accounting period. Year-end close creates a new file; the prior file becomes a read-only archive on Google Drive.

**Rationale:** A GnuCash file accumulating a decade of data grows large and contains years of history the user never consults. Each session requires downloading and uploading the entire file. Keeping the active file scoped to one period keeps it small and fast.

**What "closing the books" means mechanically:**
1. Create closing entries that zero out all income and expense accounts, rolling net income into retained earnings (equity)
2. Carry forward opening balances for all asset, liability, and equity accounts
3. Carry forward active sub-ledger positions: open investment lots, unsold fixed assets, un-matured fixed income instruments
4. Archive the closed file on Drive; create a new file for the new period

**What gets left behind in the archive:**
- All transaction and split detail for the closed period
- Sold or disposed assets
- Matured or sold fixed income instruments
- Closed investment positions
- Reconciliation history

**Soft pointer to prior period:** The `entity` table stores the Google Drive file ID of the previous period's archive in `prior_period_file_id`. This is a soft pointer — if the user moves or deletes the archive, the current file remains fully functional. The pointer enables an "open prior year" feature but is not required for normal operation.

**Sub-ledger close rules (for future module implementation):**
- Fixed income: carry forward if `is_sold = 0` and `maturity_date > close_date`
- Investments: carry forward if position is still open
- Fixed assets: carry forward if not disposed

**Note on file size:** SQLite is extremely compact. A personal finance file with ten years of household transactions would typically land between 5 MB and 20 MB. The decision to close annually is about workflow clarity and alignment with accounting practice, not about file size constraints.

---

## Decision 8: accounts.id Uses GUIDs; All Other PKs Use INTEGER

**Decision:** `accounts.id` is a 32-character lowercase hex GUID (`lower(hex(randomblob(16)))`). All other tables use `INTEGER PRIMARY KEY AUTOINCREMENT`.

**Rationale:** The chart of accounts is the one artifact that carries forward intact from one period file to the next. If account IDs were sequential integers, account #7 in the 2025 archive and account #7 in the 2026 active file could be completely different accounts, creating ambiguity in any cross-file reporting or "open prior year" feature.

With GUIDs, "Expenses:Groceries" carries the same ID across every file it ever appears in. The 2025 archive and the 2026 active file share stable, collision-free account identifiers.

Institutions, financial accounts, payees, transactions, and splits are period-scoped and do not need to survive file transitions.

---

## Decision 9: Commodities Table Covers Both Currencies and Securities

**Decision:** A single `commodities` table covers currencies (USD, EUR) and securities (AAPL, VTSAX). Every place in the schema that needs a currency or security references `commodities` by foreign key.

**Rationale:** In double-entry bookkeeping, a "commodity" is anything with value that can be tracked. USD is a commodity just like AAPL is. The only practical difference is `commodity_type`. A unified table avoids the need for separate currency and security tables and makes multi-currency and investment reporting consistent.

**Standards enforced:**
- ISO 4217 for currency symbols (3 uppercase letters, e.g. `'USD'`)
- ISO 6166 (ISIN) for international securities identifiers (12 characters)
- CUSIP for US securities identifiers (9 characters)

**`commodity_type` values:** `'currency'`, `'stock'`, `'etf'`, `'mutual_fund'`, `'other'`

---

## Decision 10: financial_account_id Lives on Splits, Not Transaction Headers

**Decision:** `financial_account_id` is a NOT NULL column on the `splits` table. It does not appear on `transactions`.

**Rationale:** Consider a restaurant meal where $20 is paid with a prepaid Visa card and $30 is paid with a debit card. This is one transaction (one payee, one expense account entry) but it touches two financial accounts. If `financial_account_id` lived on the transaction header, there would be no way to record which financial account funded which portion.

Placing it on splits means each leg of the transaction independently records which real-world account it touches. The financial account register for "Chase Checking" is simply all splits that reference it — straightforward and accurate.

**Every split must reference a financial account without exception.** There is no "Imbalance" account, no nullable escape hatch. An unbalanced or incompletely specified transaction is rejected at the database level.

---

## Decision 11: Splits Use Absolute Amounts with a Debit/Credit Flag

**Decision:** The `splits.amount` column stores an absolute (always positive) value. Direction is given by a separate `splits.debit_credit` column containing `'debit'` or `'credit'`.

**Rationale:** Using signed values (positive for debit, negative for credit) is a programmer's shortcut that works in code but creates confusion the moment an accountant reads the data. Debits and credits are unambiguous, self-documenting, and match every accounting textbook and professional convention.

**One direction per row:** A deposit and a simultaneous cash withdrawal at the same institution are two splits, not one. The debit/credit flag enforces one direction per row. A combined row with both a debit value and a credit value would be ambiguous; the single amount + flag design makes it structurally impossible.

**Double-entry integrity:** A trigger on `splits` enforces that total debits equal total credits for every transaction. This check fires after every insert or update and rejects any transaction that does not balance. There is no application-layer workaround.

---

## Decision 12: Reconciliation Status Lives on Splits

**Decision:** `reconciliation_status` (`'pending'`, `'cleared'`, `'reconciled'`) is a column on `splits`, not on `transactions`.

**Rationale:** Reconciliation happens per financial account against a specific statement. Using the restaurant example again: the Chase Checking split gets reconciled when you reconcile your checking account statement. The prepaid Visa split gets reconciled independently when you reconcile that account. They are separate reconciliation events that happen at different times. Putting reconciliation status on the transaction header would conflate two independent events.

---

## Decision 13: Sub-Ledger Architecture for Future Modules

**Decision:** Accounts that require item-level tracking (investments, fixed income, fixed assets) use a `subledger_enabled` flag and a `subledger_module` reference on the `accounts` table. The sub-ledger detail tables are implemented as separate modules that must reconcile to the general ledger account balance.

**Rationale:** The general ledger needs only one number per account: the balance. A brokerage account in the GL is simply "Assets:Investments = $150,000." The investment sub-ledger knows that this breaks down into 100 shares AAPL, 200 shares MSFT, etc. The modules are independent; the GL is always authoritative.

**Supported sub-ledger modules (future):**
- `investment` — securities: stocks, ETFs, mutual funds; cost basis, lots, gains
- `fixed_income` — CDs, Treasuries, bonds; maturity ladder, coupon payments
- `asset_tracking` — vehicles, real estate, equipment; depreciation, disposal

**Year-end close rule:** Only active sub-ledger positions carry forward to the new period file. Sold assets, matured instruments, and closed positions are left behind in the archive.

**Constraint:** An account cannot be both `is_placeholder = 1` and `subledger_enabled = 1`. Placeholder accounts are summary nodes that accept no transactions; sub-ledger accounts must accept transactions.

---

## Decision 14: Development Philosophy and Sequence

**Philosophy:** Build in small, independently testable modules. Each phase must be working and validated before the next begins. This keeps bugs easy to isolate and avoids compounding unknowns.

**Decided sequence:**

1. **Bare FastAPI scaffold** ✅ — A minimal FastAPI app running on Render.com with a single test endpoint and no authentication. Validates the hosting setup and project structure. GitHub repository established at `StephenMNolan/gnucash-web` with automatic deploys to Render on every push.

2. **Google OAuth plus Drive file I/O** ✅ — Google OAuth login flow working end to end on both localhost and Render.com. The app can create a file on the user's Google Drive and read it back by file ID. Sessions managed via signed cookies using Starlette's `SessionMiddleware`. Authlib handles the OAuth flow. Drive API accessed via `google-api-python-client`.

3. **Schema design** ✅ — Full nine-table schema designed, stress-tested against real scenarios (multi-payment transactions, reconciliation, year-end close, sub-ledger extensibility), and documented before any DDL was written.

4. **SQLite CRUD on Drive** — Implement create, read, update, and delete operations against the real schema, with the SQLite file stored on Google Drive. Includes first-run setup flow with folder picker.

5. **Entities** — Add maintenance tools for the entity record and institutions.

6. **Accounts** — Add maintenance tools for the chart of accounts.

7. **Transactions and splits** — Add maintenance tools for transaction entry and double-entry split lines.

8. **Commodities** — Add currencies and securities support.

**Note on authentication:** A local username/password system was considered for an early phase but rejected. It would create code that does not survive into production. An unauthenticated stub in phase 1 followed by Google OAuth in phase 2 is the more direct path.

**Each phase is developed and validated in its own chat session** before the next begins. The architecture decisions document is updated at the close of each phase and carried forward as context.

---

## Decision 15: OAuth Library and Session Management

**Decision:** Authlib handles the OAuth 2.0 flow. Starlette's `SessionMiddleware` with `itsdangerous` handles signed cookie sessions.

**Rationale:** Authlib integrates cleanly with FastAPI and Starlette, handles the redirect/callback dance and token management, and uses Google's OpenID Connect discovery document to locate endpoints automatically rather than hardcoding them.

Signed cookies keep the backend stateless, which is consistent with the architecture philosophy and avoids any need for a server-side session store on Render's ephemeral filesystem.

**Backend file structure established in Phase 2:**

```
backend/
├── app/
│   ├── db/
│   │   └── schema.sql   # Full database schema; used during first-run file creation
│   ├── __init__.py
│   ├── main.py          # App entry point, middleware, router registration
│   ├── auth.py          # OAuth flow endpoints (/auth/login, /auth/callback, /auth/me, /auth/logout)
│   ├── drive.py         # Google Drive API wrapper (proof of concept; will be replaced in Phase 4)
│   └── dependencies.py  # FastAPI dependencies: get_current_user, get_current_token
├── requirements.txt
├── .env.example
└── .env                 # Gitignored; contains GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY, REDIRECT_URI
```

**Known gap:** The Drive proof-of-concept endpoints (`/drive/test-write`, `/drive/test-read`) create files in the Drive root with no duplicate checking. These will be removed and replaced with proper first-run setup logic in Phase 4, including a folder picker so the user controls where `dollarcloud.db` is stored.

**Key lesson from Phase 2:** `oauth.register()` must not run at module import time. It executed before `load_dotenv()`, causing a `KeyError` on `GOOGLE_CLIENT_ID`. Resolved by wrapping in `init_oauth()` called explicitly after env vars load.

---

## Decision 16: Accounts Are Never Deleted, Only Deactivated

**Decision:** Accounts are retained permanently in the database. Closing an account sets `is_active = 0` and `closing_date`. Accounts are never deleted. This is enforced at three levels: application policy, `ON DELETE RESTRICT` on the `splits.account_id` foreign key, and the `accounts_active` view which filters inactive accounts from normal UI queries.

**Rationale — three independent reasons, each sufficient on its own:**

**Audit trail integrity.** Every split references `account_id` by foreign key. Deleting an account would orphan its historical splits, destroying the transaction record. `ON DELETE RESTRICT` prevents this at the database level, but permanent retention is the cleaner policy: the constraint becomes a last-resort guardrail rather than the primary protection.

**Cross-file GUID stability.** Account IDs are GUIDs that carry forward from one period file to the next, giving the same account a stable identity across years. If a closed account were deleted from the active file and a new account were later created that happened to receive the same GUID (probability roughly 1 in 2^128 per pair, non-zero), that new account would incorrectly match the old account's ID in any prior-year archive. Permanent retention eliminates this class of problem entirely.

**Standard accounting practice.** Charts of accounts are historical records. Closed accounts represent real economic activity that occurred under those categories. Destroying them would compromise the integrity of the historical record.

**Implementation:** The `accounts_active` view (`SELECT * FROM accounts WHERE is_active = 1`) handles filtering in all normal UI contexts. Reporting and audit queries can join directly against the `accounts` table to include closed accounts when needed.

---

## Deferred Decisions

- Specific JavaScript framework for the frontend (vanilla JS vs. Vue vs. other)
- Authentication provider beyond Google (Microsoft, Apple, etc.)
- Offline / progressive web app capabilities
- Reporting and export formats
- GnuCash import/export utility (separate tool, not a core dependency)
- Google Drive folder picker UI for first-run setup (deferred to Phase 4)
- `prices` table for historical commodity price data (schema unblocked, implementation later)
- Fixed income sub-ledger module (schema hook in place via `subledger_module = 'fixed_income'`)
- Investment positions sub-ledger (schema hook in place via `subledger_module = 'investment'`)
- Fixed asset tracking sub-ledger (schema hook in place via `subledger_module = 'asset_tracking'`)
