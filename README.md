# DollarCloud

A web-based, mobile-aware double-entry accounting application. User financial data is stored in the user's own Google Drive, not on the application server.

- **Live app:** https://dollarcloud.onrender.com
- **GitHub:** https://github.com/StephenMNolan/gnucash-web

---

## Project Structure

```
gnucash-web/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── drive.py
│   │   └── dependencies.py
│   ├── requirements.txt
│   ├── .env.example
│   └── .env               # Gitignored — never committed
├── frontend/
│   └── index.html
├── .gitignore
└── README.md
```

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

Visit http://127.0.0.1:8000 in your browser. You should see:

```json
{"message": "Hello, World!"}
```

To test the login flow, visit http://127.0.0.1:8000/auth/login. After signing in with Google you will be redirected to `/auth/me`, which returns your name and email as JSON.

The interactive API browser is available at http://127.0.0.1:8000/docs.

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

Just push to GitHub from your Mac:

```bash
git add .
git commit -m "Description of what you changed"
git push
```

Render will detect the push and redeploy automatically. No further action needed.

### Environment variables

Secret values (API keys, OAuth credentials) are set in the Render dashboard under **Environment** for your service. Never put secrets in the repository.

---

## Git Workflow (Quick Reference)

### Check what has changed

```bash
git status
```

### Stage your changes

```bash
git add .                          # Stage everything
git add backend/app/main.py        # Stage a specific file
```

### Commit and push

```bash
git commit -m "A short description of what you changed"
git push
```

### Pull the latest from GitHub

```bash
git pull
```

---

## Development Phases

- [x] Phase 1: Bare FastAPI scaffold on Render.com
- [x] Phase 2: Google OAuth and Drive file I/O
- [ ] Phase 3: Schema design
- [ ] Phase 4: SQLite CRUD on Drive
- [ ] Phase 5: Entities
- [ ] Phase 6: Accounts
- [ ] Phase 7: Transactions and splits
- [ ] Phase 8: Commodities
