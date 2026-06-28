-- ============================================================================
-- DOLLARCLOUD - DATABASE SCHEMA
-- ============================================================================
-- Version: 1.0
-- Phase: 3 (Schema Design)
--
-- This schema implements a dual-layer architecture:
--
--   FINANCIAL LAYER  — "where money lives"
--     institutions, financial_accounts
--
--   ACCOUNTING LAYER — "how it's categorized"
--     accounts (chart of accounts), transactions, splits
--
--   SUPPORT TABLES
--     entity, commodities, payees
--
-- Design Philosophy: "Hood Up vs Driver's Seat"
--   Strict double-entry accounting integrity underneath.
--   Intuitive personal finance interface on top.
--   The two layers are linked through splits, which reference both
--   an accounting account (what/why) and a financial account (where).
--
-- Key Architectural Decisions:
--   - One file per entity, one entity per file
--   - Annual (or periodic) close creates a new file; prior file is archived
--   - Every split must reference both an accounting account and a financial
--     account — no exceptions, no escape hatches
--   - Splits use absolute amounts + a debit/credit flag (never signed values)
--   - accounts.id is a GUID for cross-file stability across period closings
--   - All other primary keys are INTEGER
--   - commodities covers both currencies and securities; referenced by FK
--     everywhere a currency or security is needed
--
-- Deferred Tables (not in this schema):
--   prices                — historical price data per commodity per date
--   fixed_income_instruments — fixed income sub-ledger (Phase: future)
--   investment_positions  — investment sub-ledger (Phase: future)
--   assets                — fixed asset sub-ledger (Phase: future)
-- ============================================================================


PRAGMA foreign_keys = ON;


-- ============================================================================
-- SECTION 1: ENTITY
-- Single-row header record for this file.
-- One file = one entity = one set of books.
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
        -- Always 1. Enforces single-row constraint at the database level.

    name                    TEXT NOT NULL,
        -- Display name: "Stephen Nolan" or "Nolan Household"

    base_currency_id        INTEGER NOT NULL REFERENCES commodities(id),
        -- The default currency for this set of books.

    fiscal_year_start_month INTEGER NOT NULL DEFAULT 1
        CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
        -- 1 = January. Most users will use 1.

    timezone                TEXT NOT NULL DEFAULT 'America/Chicago',
        -- IANA timezone name. Used for date display and period boundary logic.

    closing_frequency       TEXT NOT NULL DEFAULT 'annual'
        CHECK (closing_frequency IN ('annual', 'quarterly', 'monthly')),
        -- How often the user closes their books and starts a new file.

    current_period_start    TEXT NOT NULL,
        -- ISO 8601 date. The start of this file's open period.
        -- Updated each time books are closed and a new file is created.

    last_closed_at          TEXT,
        -- ISO 8601 timestamp. When the previous file was closed and
        -- this one was created. NULL for a brand-new first file.

    prior_period_file_id    TEXT,
        -- Google Drive file ID of the previous period's archive file.
        -- Soft pointer — if the user moves or deletes the archive,
        -- this simply won't resolve. The current file is always
        -- self-contained and fully functional without it.

    schema_version          TEXT NOT NULL DEFAULT '1.0',
        -- For migration detection. Increment when schema changes.

    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    preferences             JSON
        -- Catch-all for UI preferences: column widths, localization
        -- overrides, theme, display density, etc.
        -- Anything that needs to be queried or constrained gets its own
        -- typed column above. Everything else lives here.
);

CREATE TRIGGER IF NOT EXISTS entity_updated_at
    AFTER UPDATE ON entity
    FOR EACH ROW
BEGIN
    UPDATE entity SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;


-- ============================================================================
-- SECTION 2: COMMODITIES
-- Currencies, stocks, ETFs, and mutual funds.
-- Both "USD" and "AAPL" are commodities. The difference is commodity_type.
-- Referenced by FK everywhere a currency or security is needed.
-- ============================================================================

CREATE TABLE IF NOT EXISTS commodities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    symbol          TEXT NOT NULL,
        -- ISO 4217 for currencies ('USD', 'EUR'), ticker for securities ('AAPL')

    name            TEXT NOT NULL,
        -- 'US Dollar', 'Apple Inc.', 'Vanguard Total Stock Market Index Fund'

    commodity_type  TEXT NOT NULL
        CHECK (commodity_type IN ('currency', 'stock', 'etf', 'mutual_fund', 'other')),

    cusip           TEXT CHECK (cusip IS NULL OR length(cusip) = 9),
        -- 9-character CUSIP identifier. NULL for currencies.

    isin            TEXT CHECK (isin IS NULL OR length(isin) = 12),
        -- 12-character ISO 6166 identifier. NULL for currencies.

    exchange        TEXT,
        -- 'NYSE', 'NASDAQ', etc. NULL for currencies.

    price_source    TEXT,
        -- Future use: where to fetch price data for this commodity.

    is_active       INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Symbol must be unique within a commodity type
    UNIQUE (symbol, commodity_type),

    -- ISO 4217: currency symbols must be exactly 3 uppercase letters
    CHECK (commodity_type != 'currency' OR (
        length(symbol) = 3 AND symbol = upper(symbol)
    )),

    -- Currencies do not trade on exchanges
    CHECK (commodity_type != 'currency' OR exchange IS NULL)
);

CREATE TRIGGER IF NOT EXISTS commodities_updated_at
    AFTER UPDATE ON commodities
    FOR EACH ROW
BEGIN
    UPDATE commodities SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_commodities_symbol ON commodities(symbol);
CREATE INDEX IF NOT EXISTS idx_commodities_type   ON commodities(commodity_type);


-- ============================================================================
-- SECTION 3: INSTITUTIONS
-- Organizations that hold real-world accounts: banks, brokerages,
-- credit unions, credit card companies, mortgage companies, etc.
-- One institution -> many financial accounts.
-- ============================================================================

CREATE TABLE IF NOT EXISTS institutions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    name        TEXT NOT NULL UNIQUE,
        -- 'Chase Bank', 'Fidelity Investments', 'Navy Federal Credit Union'

    website     TEXT,
    username    TEXT,
        -- Login username only. Never a password.
        -- Stored as a convenience for the user, not used by the app.

    icon_url    TEXT,
        -- Remote icon URL (e.g. institution favicon). No local path
        -- because DollarCloud is a web app with no local filesystem.

    notes       TEXT,
    metadata    JSON,
        -- Extensible: OFX URLs, API settings, contact info, etc.

    is_active   INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TRIGGER IF NOT EXISTS institutions_updated_at
    AFTER UPDATE ON institutions
    FOR EACH ROW
BEGIN
    UPDATE institutions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_institutions_name ON institutions(name);


-- ============================================================================
-- SECTION 4: FINANCIAL ACCOUNTS
-- Real-world accounts at institutions.
-- Chase Checking #1234, Fidelity brokerage #5678, etc.
--
-- CRITICAL DISTINCTION:
--   financial_accounts = "where money lives" (real-world)
--   accounts           = "how it's categorized" (accounting)
--
-- One Fidelity brokerage account (#123456789) might contain:
--   Stocks  -> Assets:Investments:Stocks
--   Bonds   -> Assets:Investments:Bonds
--   Cash    -> Assets:Current Assets:Cash
-- These are separate accounting accounts but ONE financial account.
-- ============================================================================

CREATE TABLE IF NOT EXISTS financial_accounts (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,

    institution_id              INTEGER NOT NULL
        REFERENCES institutions(id) ON DELETE RESTRICT,

    name                        TEXT NOT NULL,
        -- 'Main Checking', 'Roth IRA', 'Brokerage Account'

    account_number              TEXT,
        -- Masked for security: '****1234'. Never store full account numbers.

    account_type                TEXT NOT NULL CHECK (account_type IN (
        -- Banking
        'checking', 'savings', 'money_market', 'cd',
        -- Investment
        'brokerage', 'retirement_401k', 'retirement_ira',
        'retirement_roth', 'hsa',
        -- Credit
        'credit_card', 'line_of_credit',
        -- Loans
        'mortgage', 'auto_loan', 'personal_loan', 'student_loan',
        -- Catch-all
        'other'
    )),

    currency_id                 INTEGER NOT NULL
        REFERENCES commodities(id),
        -- Must reference a commodity where commodity_type = 'currency'

    routing_number              TEXT,   -- ACH routing number
    swift_code                  TEXT,   -- International wire transfers
    phone                       TEXT,   -- Institution phone for this account
    url                         TEXT,   -- Direct link to account page online

    default_account_id          TEXT
        REFERENCES accounts(id) ON DELETE SET NULL,
        -- Optional convenience bridge to the accounting layer.
        -- Suggested chart-of-accounts mapping for transaction entry.
        -- Not a constraint — the user can always override it.

    tax_advantaged              TEXT CHECK (tax_advantaged IN (
        '401k', 'ira', 'roth', 'hsa', NULL
    )),
        -- Explicit flag for tax-advantaged account types.

    reconciliation_enabled      INTEGER NOT NULL DEFAULT 1
        CHECK (reconciliation_enabled IN (0, 1)),

    last_reconciled_date        TEXT,   -- ISO 8601 date
    last_statement_date         TEXT,   -- ISO 8601 date
    last_statement_balance      REAL,

    is_active                   INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    opening_date                TEXT,   -- ISO 8601 date
    closing_date                TEXT,   -- ISO 8601 date; required when is_active = 0

    notes                       TEXT,
    metadata                    JSON,
        -- Extensible: credit limits, interest rates, loan terms, etc.

    created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    CHECK (is_active = 1 OR closing_date IS NOT NULL)
        -- A closed account must have a closing date.
);

CREATE TRIGGER IF NOT EXISTS financial_accounts_updated_at
    AFTER UPDATE ON financial_accounts
    FOR EACH ROW
BEGIN
    UPDATE financial_accounts
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_financial_accounts_institution
    ON financial_accounts(institution_id);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_type
    ON financial_accounts(account_type);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_active
    ON financial_accounts(is_active) WHERE is_active = 1;


-- ============================================================================
-- SECTION 5: ACCOUNTS (CHART OF ACCOUNTS)
-- The accounting layer. Pure double-entry categories.
-- Hierarchical structure via materialized path.
--
-- These are NOT the same as financial_accounts.
-- 'Assets:Current Assets:Checking' is an accounting account.
-- 'Chase Checking #1234' is a financial account.
--
-- accounts.id is a GUID (not INTEGER) for cross-file stability.
-- When books are closed and a new period file is created, the chart
-- of accounts carries forward intact with the same GUIDs, so that
-- prior-year archive files and the current file share stable identifiers.
-- ============================================================================

CREATE TABLE IF NOT EXISTS accounts (
    id              TEXT PRIMARY KEY
                    DEFAULT (lower(hex(randomblob(16)))),
        -- 32-character GUID. Stable across period file closings.

    account_code    TEXT UNIQUE,
        -- Optional user-defined hierarchical code: '1000', '1100.01'
        -- NULL if not used.

    name            TEXT NOT NULL,
    description     TEXT,

    -- -----------------------------------------------------------------------
    -- Hierarchy
    -- -----------------------------------------------------------------------
    parent_id       TEXT REFERENCES accounts(id) ON DELETE RESTRICT,
        -- NULL for root accounts (Assets, Liabilities, Equity, Income, Expenses)
        -- ON DELETE RESTRICT prevents deletion of parent accounts with children.

    path            TEXT NOT NULL CHECK (length(path) > 0),
        -- Materialized path for efficient hierarchy queries.
        -- Format: '/parent_guid/this_guid/'
        -- Enables subtree queries with a simple LIKE '/root/%' pattern.

    depth           INTEGER NOT NULL DEFAULT 0,
        -- 0 = root account. Auto-calculated from path length.

    next_sibling_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
        -- Linked list for user-controlled display order within siblings.
        -- NULL = last account among siblings.

    -- -----------------------------------------------------------------------
    -- Classification
    -- -----------------------------------------------------------------------
    account_type    TEXT NOT NULL CHECK (account_type IN (
        'ASSETS', 'LIABILITIES', 'EQUITY', 'INCOME', 'EXPENSES'
    )),

    normal_balance  TEXT NOT NULL CHECK (normal_balance IN ('DEBIT', 'CREDIT')),
        -- ASSETS and EXPENSES increase with DEBIT.
        -- LIABILITIES, EQUITY, and INCOME increase with CREDIT.
        -- Contra-accounts have the opposite normal balance from their type.

    currency_id     INTEGER NOT NULL REFERENCES commodities(id),
        -- Must reference a commodity where commodity_type = 'currency'

    -- -----------------------------------------------------------------------
    -- Operational Flags
    -- -----------------------------------------------------------------------
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),

    is_placeholder  INTEGER NOT NULL DEFAULT 0 CHECK (is_placeholder IN (0, 1)),
        -- 1 = parent/summary account only. Transactions not allowed.
        -- 0 = transactions allowed (leaf account).

    -- -----------------------------------------------------------------------
    -- Sub-Ledger Support
    -- Accounts flagged for sub-ledger tracking are managed by a specialized
    -- module that maintains item-level detail summing to this account's balance.
    -- Example: GL 'Brokerage Assets' = $150,000
    --   SL: 100 shares AAPL @ $180, 200 shares MSFT @ $380, etc.
    -- -----------------------------------------------------------------------
    subledger_enabled   INTEGER NOT NULL DEFAULT 0 CHECK (subledger_enabled IN (0, 1)),
    subledger_module    TEXT CHECK (subledger_module IN (
        'investment', 'fixed_income', 'asset_tracking', NULL
    )),

    -- -----------------------------------------------------------------------
    -- Tax Tracking
    -- -----------------------------------------------------------------------
    tax_related     INTEGER NOT NULL DEFAULT 0 CHECK (tax_related IN (0, 1)),
        -- Hint that transactions in this account may have tax implications.

    tax_form        TEXT,
        -- Expected tax form: '1099-INT', 'W-2', '1098', etc.

    -- -----------------------------------------------------------------------
    -- Dates and Metadata
    -- -----------------------------------------------------------------------
    opening_date    TEXT,   -- ISO 8601 date
    closing_date    TEXT,   -- ISO 8601 date; required when is_active = 0

    metadata        JSON,

    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- -----------------------------------------------------------------------
    -- Constraints
    -- -----------------------------------------------------------------------
    CHECK (NOT (is_placeholder = 1 AND subledger_enabled = 1)),
        -- An account cannot be both a placeholder and a sub-ledger account.

    CHECK (subledger_module IS NULL OR subledger_enabled = 1),
        -- A sub-ledger module may only be set when sub-ledger is enabled.

    CHECK (next_sibling_id != id),
        -- Prevent self-referencing in the linked list.

    CHECK (parent_id != id),
        -- Prevent self-parenting.

    CHECK (is_active = 1 OR closing_date IS NOT NULL)
        -- An inactive account must have a closing date.
);

CREATE TRIGGER IF NOT EXISTS accounts_updated_at
    AFTER UPDATE ON accounts
    FOR EACH ROW
BEGIN
    UPDATE accounts SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

-- Enforce closing_date when marking account inactive
CREATE TRIGGER IF NOT EXISTS accounts_validate_closing
    BEFORE UPDATE OF is_active ON accounts
    FOR EACH ROW
    WHEN NEW.is_active = 0 AND NEW.closing_date IS NULL
BEGIN
    SELECT RAISE(ABORT, 'closing_date must be set when marking an account inactive');
END;

CREATE INDEX IF NOT EXISTS idx_accounts_type
    ON accounts(account_type);
CREATE INDEX IF NOT EXISTS idx_accounts_parent
    ON accounts(parent_id);
CREATE INDEX IF NOT EXISTS idx_accounts_path
    ON accounts(path);
CREATE INDEX IF NOT EXISTS idx_accounts_active
    ON accounts(is_active) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_accounts_subledger
    ON accounts(subledger_module) WHERE subledger_enabled = 1;
CREATE INDEX IF NOT EXISTS idx_accounts_currency
    ON accounts(currency_id);
CREATE INDEX IF NOT EXISTS idx_accounts_next_sibling
    ON accounts(next_sibling_id);
CREATE INDEX IF NOT EXISTS idx_accounts_code
    ON accounts(account_code) WHERE account_code IS NOT NULL;


-- ============================================================================
-- VIEWS FOR ACCOUNTS
-- ============================================================================

-- Identify contra-accounts (opposite normal balance from account type)
CREATE VIEW IF NOT EXISTS accounts_with_contra_flag AS
SELECT
    *,
    CASE
        WHEN account_type IN ('ASSETS', 'EXPENSES')      AND normal_balance = 'CREDIT' THEN 1
        WHEN account_type IN ('LIABILITIES', 'EQUITY', 'INCOME') AND normal_balance = 'DEBIT' THEN 1
        ELSE 0
    END AS is_contra
FROM accounts;

-- Active accounts only (most common UI filter)
CREATE VIEW IF NOT EXISTS accounts_active AS
SELECT * FROM accounts WHERE is_active = 1;

-- Human-readable full path names for display (e.g. "Assets > Current Assets > Checking")
CREATE VIEW IF NOT EXISTS accounts_with_full_path AS
SELECT
    a.id,
    a.name,
    a.account_type,
    a.parent_id,
    a.depth,
    a.path,
    GROUP_CONCAT(p.name, ' > ') AS full_path_name
FROM accounts a
LEFT JOIN accounts p
    ON a.path LIKE '%' || p.id || '%' AND p.id != a.id
GROUP BY a.id
ORDER BY a.path;


-- ============================================================================
-- SECTION 6: PAYEES
-- Entities you transact with: merchants, employers, utilities, individuals.
-- Referenced by transactions. Separate from institutions (which hold accounts).
--
-- Chase can be both:
--   Institution: holds your checking account
--   Payee: you pay your Chase credit card bill
-- Different roles, different tables. The overlap is intentional and correct.
-- ============================================================================

CREATE TABLE IF NOT EXISTS payees (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    name                    TEXT NOT NULL UNIQUE,
        -- 'HEB', 'Austin Energy', 'Employer Name', 'IRS'

    payee_type              TEXT CHECK (payee_type IN (
        'employer', 'vendor', 'merchant', 'utility', 'government',
        'individual', 'financial_services', 'other', NULL
    )),
        -- 'other' covers ORRI operators and any other unlisted type.

    tax_id                  TEXT,
        -- EIN or SSN for 1099 threshold tracking. Never a password or secret.

    tax_entity_type         TEXT CHECK (tax_entity_type IN (
        'individual', 'sole_proprietor', 'partnership', 'llc',
        'corporation', 's_corp', 'non_profit', NULL
    )),

    default_account_id      TEXT REFERENCES accounts(id) ON DELETE SET NULL,
        -- Suggested accounting category for auto-categorization.

    notes                   TEXT,
    metadata                JSON,
        -- Extensible: aliases for fuzzy import matching, address,
        -- phone, auto-categorization rules, etc.

    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TRIGGER IF NOT EXISTS payees_updated_at
    AFTER UPDATE ON payees
    FOR EACH ROW
BEGIN
    UPDATE payees SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_payees_name    ON payees(name);
CREATE INDEX IF NOT EXISTS idx_payees_type    ON payees(payee_type);
CREATE INDEX IF NOT EXISTS idx_payees_tax_id  ON payees(tax_id) WHERE tax_id IS NOT NULL;


-- ============================================================================
-- SECTION 7: TRANSACTIONS
-- Transaction header. One record per financial event.
-- The payee and narrative live here. The money movement lives in splits.
--
-- A transaction with no splits is invalid. The double-entry balance check
-- (total debits = total credits) is enforced by trigger on the splits table.
-- ============================================================================

CREATE TABLE IF NOT EXISTS transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    date                TEXT NOT NULL,
        -- ISO 8601 date. The accounting date — canonical for your books.

    institution_date    TEXT,
        -- ISO 8601 date. The date the institution recorded the transaction.
        -- Often the same as date, but diverges for checks, ACH delays, etc.
        -- Reconciliation uses institution_date. Reports use date.

    description         TEXT,
    payee_id            INTEGER REFERENCES payees(id) ON DELETE SET NULL,

    is_opening_balance  INTEGER NOT NULL DEFAULT 0 CHECK (is_opening_balance IN (0, 1)),
        -- 1 = this transaction carries forward a balance from the prior period.
        -- Used during year-end close to seed the new file.

    is_closing_entry    INTEGER NOT NULL DEFAULT 0 CHECK (is_closing_entry IN (0, 1)),
        -- 1 = this transaction is a year-end closing entry that zeros out
        -- income and expense accounts and rolls net into retained earnings.

    check_number        TEXT,
    notes               TEXT,
    metadata            JSON,

    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TRIGGER IF NOT EXISTS transactions_updated_at
    AFTER UPDATE ON transactions
    FOR EACH ROW
BEGIN
    UPDATE transactions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_transactions_date
    ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_payee
    ON transactions(payee_id);
CREATE INDEX IF NOT EXISTS idx_transactions_opening
    ON transactions(is_opening_balance) WHERE is_opening_balance = 1;
CREATE INDEX IF NOT EXISTS idx_transactions_closing
    ON transactions(is_closing_entry) WHERE is_closing_entry = 1;


-- ============================================================================
-- SECTION 8: SPLITS
-- The double-entry legs of every transaction.
-- Every transaction has two or more splits that must balance:
--   total debits = total credits
--
-- Each split references:
--   account_id           — WHAT/WHY: the accounting category
--   financial_account_id — WHERE: the real-world account
--
-- Both references are NOT NULL. Every dollar in the system is always
-- traceable to both an accounting category and a real-world account.
-- There are no exceptions and no escape hatches.
--
-- Amounts use absolute values with a debit_credit flag, not signed values.
-- This matches standard accounting practice and avoids sign-convention errors.
--
-- Reconciliation status lives on splits, not on transaction headers, because
-- reconciliation happens per financial account. The checking account split
-- and the prepaid card split on the same transaction reconcile independently.
-- ============================================================================

CREATE TABLE IF NOT EXISTS splits (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    transaction_id          INTEGER NOT NULL
        REFERENCES transactions(id) ON DELETE RESTRICT,
        -- ON DELETE RESTRICT: cannot delete a transaction that has splits.
        -- Splits must be deleted first.

    account_id              TEXT NOT NULL
        REFERENCES accounts(id) ON DELETE RESTRICT,
        -- The accounting category. Must be a non-placeholder account.

    financial_account_id    INTEGER NOT NULL
        REFERENCES financial_accounts(id) ON DELETE RESTRICT,
        -- The real-world account. NOT NULL — every split must be traceable
        -- to a financial account.

    amount                  REAL NOT NULL CHECK (amount > 0),
        -- Absolute value. Always positive. Direction is given by debit_credit.

    debit_credit            TEXT NOT NULL CHECK (debit_credit IN ('debit', 'credit')),
        -- 'debit'  = increases ASSETS and EXPENSES accounts
        -- 'credit' = increases LIABILITIES, EQUITY, and INCOME accounts
        -- One direction per row. A deposit and simultaneous cash withdrawal
        -- at the same institution are two splits, not one.

    memo                    TEXT,
        -- Split-level note. Distinct from the transaction-level description.

    reconciliation_status   TEXT NOT NULL DEFAULT 'pending'
        CHECK (reconciliation_status IN ('pending', 'cleared', 'reconciled')),
        -- pending    = entered but not yet seen on a statement
        -- cleared    = appears on a statement; reconciliation not yet completed
        -- reconciled = included in a completed reconciliation

    reconciled_date         TEXT,
        -- ISO 8601 date. Required when reconciliation_status = 'reconciled'.

    tax_form                TEXT,
        -- e.g. '1099-INT', 'W-2', '1098'. Split-level tax tracking.

    tax_category            TEXT,
        -- More specific tax line item within the form.

    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    CHECK (reconciliation_status != 'reconciled' OR reconciled_date IS NOT NULL)
        -- A reconciled split must have a reconciled_date.
);

CREATE TRIGGER IF NOT EXISTS splits_updated_at
    AFTER UPDATE ON splits
    FOR EACH ROW
BEGIN
    UPDATE splits SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

-- Enforce that splits on a placeholder account are not allowed
CREATE TRIGGER IF NOT EXISTS splits_no_placeholder_account
    BEFORE INSERT ON splits
    FOR EACH ROW
    WHEN (SELECT is_placeholder FROM accounts WHERE id = NEW.account_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'Splits cannot be posted to placeholder accounts');
END;

-- Enforce double-entry balance: total debits = total credits per transaction
-- This fires after every insert or update on splits.
CREATE TRIGGER IF NOT EXISTS splits_balance_check_insert
    AFTER INSERT ON splits
    FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Transaction does not balance: total debits must equal total credits')
    WHERE (
        SELECT
            ABS(
                SUM(CASE WHEN debit_credit = 'debit'  THEN amount ELSE 0 END) -
                SUM(CASE WHEN debit_credit = 'credit' THEN amount ELSE 0 END)
            )
        FROM splits
        WHERE transaction_id = NEW.transaction_id
    ) > 0.001;
        -- 0.001 tolerance for floating-point rounding. In practice, all amounts
        -- should balance exactly. Phase 4 will enforce two-decimal precision
        -- at the application layer before values reach the database.
END;

CREATE TRIGGER IF NOT EXISTS splits_balance_check_update
    AFTER UPDATE ON splits
    FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Transaction does not balance: total debits must equal total credits')
    WHERE (
        SELECT
            ABS(
                SUM(CASE WHEN debit_credit = 'debit'  THEN amount ELSE 0 END) -
                SUM(CASE WHEN debit_credit = 'credit' THEN amount ELSE 0 END)
            )
        FROM splits
        WHERE transaction_id = NEW.transaction_id
    ) > 0.001;
END;

CREATE INDEX IF NOT EXISTS idx_splits_transaction
    ON splits(transaction_id);
CREATE INDEX IF NOT EXISTS idx_splits_account
    ON splits(account_id);
CREATE INDEX IF NOT EXISTS idx_splits_financial_account
    ON splits(financial_account_id);
CREATE INDEX IF NOT EXISTS idx_splits_reconciliation
    ON splits(reconciliation_status);
CREATE INDEX IF NOT EXISTS idx_splits_tax_form
    ON splits(tax_form) WHERE tax_form IS NOT NULL;


-- ============================================================================
-- INITIAL DATA
-- Seed the five root accounting accounts that every set of books requires.
-- These are inserted during first-run file creation.
-- ============================================================================

INSERT OR IGNORE INTO accounts (id, name, account_type, normal_balance, is_placeholder, path, depth) VALUES
    ('assets_root',      'Assets',      'ASSETS',      'DEBIT',  1, '/assets_root/',      0),
    ('liabilities_root', 'Liabilities', 'LIABILITIES', 'CREDIT', 1, '/liabilities_root/', 0),
    ('equity_root',      'Equity',      'EQUITY',       'CREDIT', 1, '/equity_root/',      0),
    ('income_root',      'Income',      'INCOME',       'CREDIT', 1, '/income_root/',      0),
    ('expenses_root',    'Expenses',    'EXPENSES',     'DEBIT',  1, '/expenses_root/',    0);
    -- Note: currency_id must be set by the application during first-run setup
    -- once the base currency commodity record has been created.


-- ============================================================================
-- SCHEMA VALIDATION QUERIES
-- Run manually after schema creation to verify integrity.
-- ============================================================================

/*
PRAGMA foreign_keys;

SELECT name FROM sqlite_master WHERE type = 'table'   ORDER BY name;
SELECT name FROM sqlite_master WHERE type = 'index'   ORDER BY name;
SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name;
SELECT name FROM sqlite_master WHERE type = 'view'    ORDER BY name;

SELECT COUNT(*) AS account_count FROM accounts;
SELECT id, name, account_type, depth, path FROM accounts ORDER BY path;
*/


-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
