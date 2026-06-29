# DollarCloud

A web-based, mobile-aware double-entry accounting application. User financial data is stored in the user's own Google Drive, not on the application server.

- **Live app:** https://dollarcloud.onrender.com
- **GitHub:** https://github.com/StephenMNolan/gnucash-web

---

## What DollarCloud Is

DollarCloud combines the mathematical integrity of double-entry accounting with the practical usability of institution-centric personal finance tracking. It is designed to fix the things that make GnuCash frustrating for personal use:

- **No "Imbalance" accounts.** Every transaction must balance. Unbalanced entries are rejected at the database level.
- **Clean year-end close.** Books are closed annually (or quarterly, or monthly). The active file stays small and fast. Prior-year archives live on Google Drive and can be opened when needed.
- **Your data is yours.** The SQLite database file lives on your Google Drive. You can see it, copy it, move it, or delete it without any involvement from the app.
- **Proper account separation.** "Chase Checking #1234" (a financial account) and "Assets:Current Assets:Checking" (an accounting account) are different things. DollarCloud keeps them separate so that a single brokerage account can hold stocks, bonds, and cash — each categorized correctly — without the GnuCash workaround of one accounting account per institution account.

---

## Project Structure

```
gnucash-web/
├── backend/
│   ├── app/
│   │   ├── db/
│   │   │   ├── __init__.py    # Makes app/db a Python package
│   │   │   ├── schema.sql     # Full database schema
│   │   │   ├── database.py    # SQLite lifecycle: download, schema, upload
│   │   │   └── setup.py       # First-run setup flow and endpoints
│   │   ├── __init__.py
│   │   ├── main.py            # App entry point, middleware, routers
│   │   ├── auth.py            # OAuth flow endpoints
│   │   ├── drive.py           # Google Drive API wrapper
│   │   └── dependencies.py    # FastAPI dependencies
│   ├── requirements.txt
│   ├── .env.example
│   └── .env               # Gitignored — never committed
├── frontend/
│   └── index.html
├── architecture-decisions.md
├── .gitignore
└── README.md
```

---

## Database Architecture

DollarCloud uses a **dual-layer architecture** that cleanly separates "where money lives" from "how it's categorized."

### The Two Layers

**Financial Layer — where money lives**

| Table | Purpose |
|---|---|
| `institutions` | Banks, brokerages, credit unions |
| `financial_accounts` | Real-world accounts: Chase Checking #1234, Fidelity brokerage #5678 |

**Accounting Layer — how it's categorized**

| Table | Purpose |
|---|---|
| `accounts` | Chart of accounts; hierarchical double-entry categories |
| `transactions` | Transaction header: date, payee, narrative |
| `splits` | Double-entry legs; the bridge between the two layers |

**Support Tables**

| Table | Purpose |
|---|---|
| `entity` | Single-row file header: owner name, base currency, period dates, UI preferences |
| `commodities` | Currencies and securities; referenced everywhere a currency or security is needed |
| `payees` | Merchants, employers, counterparties |

### How a Transaction Works

```
You pay $50 at HEB, split: $30 from Chase Checking, $20 from a prepaid Visa.

Transaction header:
  date: 2026-01-15
  payee: HEB

Split 1 (the expense):
  accounting account: Expenses:Groceries
  financial account:  Chase Checking #1234
  amount: $30   debit

Split 2 (Chase funding):
  accounting account: Assets:Current Assets:Checking
  financial account:  Chase Checking #1234
  amount: $30   credit

Split 3 (prepaid Visa funding):
  accounting account: Assets:Prepaid Cards:Visa
  financial account:  Prepaid Visa Card
  amount: $20   credit

Split 4 (the expense, prepaid portion):
  accounting account: Expenses:Groceries
  financial account:  Prepaid Visa Card
  amount: $20   debit

Total debits = $50. Total credits = $50. Balanced.
```

Every split must reference both an accounting account and a financial account. There are no exceptions. The database rejects any transaction where debits do not equal credits.

### Year-End Close

At the end of each period:

1. Closing entries zero out income and expense accounts, rolling net income into retained earnings
2. Opening balance entries seed the new file with asset, liability, and equity balances
3. Active sub-ledger positions carry forward (open investments, unsold assets, un-matured fixed income instruments)
4. The closed file is archived on Google Drive; a new file is created for the new period

The `entity` table stores the Google Drive file ID of the previous archive, enabling an "open prior year" feature without requiring the app to manage a complex file inventory.

### Sub-Ledger Architecture

Accounts that require item-level tracking (investments, fixed income instruments, fixed assets) use a `subledger_enabled` flag. The general ledger holds the account balance; a specialized sub-ledger module maintains the detail.

```
GL:  Assets:Investments = $150,000
SL:  100 shares AAPL @ $180  =  $18,000
     200 shares MSFT @ $380  =  $76,000
     ...
```

Sub-ledger modules are planned for future phases:
- `investment` — stocks, ETFs, mutual funds; cost basis, lots, realized/unrealized gains
- `fixed_income` — CDs, Treasuries, bonds; maturity ladder, coupon payments
- `asset_tracking` — vehicles, real estate, equipment; depreciation, disposal

The schema hooks (`subledger_enabled`, `subledger_module`) are in place now so no schema migration will be needed when these modules are built.

---

## Local Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/StephenMNolan/gnucash-web.git
cd gnucash-web
```

### 2. Create and activate a virtual environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Open .env and fill in your values
```

The following variables are required:

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | From Google Auth Platform |
| `GOOGLE_CLIENT_SECRET` | From Google Auth Platform |
| `SECRET_KEY` | Random hex string for signing session cookies. Generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `REDIRECT_URI` | `http://localhost:8000/auth/callback` for local dev |

### 5. Run the development server

```bash
uvicorn app.main:app --reload
```

Visit http://localhost:8000 in your browser. You should see:

```json
{"message": "Hello, World!"}
```

To test the login flow, visit http://localhost:8000/auth/login in your browser (not via the Swagger UI — OAuth redirects require full browser navigation). After signing in with Google you will be redirected to `/auth/me`, which returns your name and email as JSON.

The interactive API browser is available at http://localhost:8000/docs. Open this in the same browser after completing the login flow so the session cookie carries over.

The `--reload` flag restarts the server automatically whenever you save a file. Remove it in production.

---

## Deploying to Render.com

Render deploys automatically on every push to the `main` branch. There is no manual deployment step.

### First-time setup

1. Log in to https://render.com
2. Click **New > Web Service**
3. Connect your GitHub account and select the `gnucash-web` repository
4. Fill in the following settings:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
5. Click **Deploy Web Service**

### Updating the app

```bash
git add .
git commit -m "Description of what you changed"
git push
```

Render detects the push and redeploys automatically.

### Environment variables

Secret values (API keys, OAuth credentials) are set in the Render dashboard under **Environment** for your service. Never put secrets in the repository.

---

## Git Workflow (Quick Reference)

```bash
git status                          # Check what has changed
git add .                           # Stage everything
git add backend/app/main.py         # Stage a specific file
git commit -m "Short description"
git push
git pull                            # Pull latest from GitHub
```

---

## Development Philosophy

Development proceeds in small, independently testable increments. Each phase is developed and validated in its own chat session before the next begins. No phase begins until the previous one is working and deployed.

**Module size discipline:** No module exceeds approximately 500 lines. Anything larger is split into focused sub-modules. This keeps the codebase navigable, makes bugs easy to isolate, and enforces clean separation of concerns.

**Two-track development strategy:**

The schema already contains everything needed for both an accounting view and a personal finance view. However, building both simultaneously would be needlessly complex. Instead, development proceeds in two tracks:

**Track 1 — Accounting View (current focus)**
Build a fully functional web-based double-entry accounting application: a GnuCash equivalent in the browser. This means chart of accounts management, transaction entry with debits and credits, trial balance, and basic financial statements. The accounting layer is the foundation everything else depends on, so it gets built first and proven before anything is added on top.

**Track 2 — Personal Finance View (future)**
Once Track 1 is solid, add the institution-centric personal finance layer: banks and brokerages, reconciliation against statements, payee management, and the "Driver's Seat" presentation mode. The schema and architecture already support this. No Track 1 decisions should impede Track 2, but Track 2 is not built until Track 1 is working well.

---

## Development Phases

### Completed

- [x] Phase 1: Bare FastAPI scaffold on Render.com
- [x] Phase 2: Google OAuth and Drive file I/O
- [x] Phase 3: Schema design
- [x] Phase 4: SQLite CRUD on Drive — database lifecycle, first-run setup flow, existing file detection, session-stored file ID

### Track 1 — Accounting View

- [ ] Phase 5: Entity module — entity record management, base currency, period settings
- [ ] Phase 6: Commodities module — currency management (securities deferred to Track 2)
- [ ] Phase 7: Chart of accounts — account hierarchy, create/edit/deactivate, account types
- [ ] Phase 8: Transaction entry — double-entry transaction and split management
- [ ] Phase 9: Reports — trial balance, balance sheet, income statement

### Track 2 — Personal Finance View (future, after Track 1 is proven)

- [ ] Institutions module — banks, brokerages, credit unions
- [ ] Financial accounts module — real-world account management, reconciliation
- [ ] Payees module — merchant and counterparty management, auto-categorization
- [ ] Reconciliation workflow — match splits to institution statements
- [ ] Personal finance reports — net worth, spending analysis, cash flow

### Deferred Modules (schema hooks in place)

- Fixed income sub-ledger (CDs, Treasuries, coupon tracking)
- Investment positions sub-ledger (shares, cost basis, lots)
- Fixed asset tracking sub-ledger (plant, property, equipment, inventory)
- Historical prices table
- GnuCash import/export utility
