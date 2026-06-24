# GnuCash Web

A web-based, mobile-aware double-entry accounting application. User financial data is stored in the user's own Google Drive, not on the application server.

---

## Project Structure

```
gnucash-web/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── index.html
├── .gitignore
└── README.md
```

---

## Local Development Setup

These steps get the backend running on your own machine before touching PythonAnywhere.

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/gnucash-web.git
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
# Open .env and fill in any values you need
```

### 5. Run the development server

```bash
uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000 in your browser. You should see:

```json
{"message": "Hello, World!"}
```

The `--reload` flag restarts the server automatically whenever you save a file. Remove it in production.

---

## Deploying to PythonAnywhere

### First-time setup

#### Step 1 — Create a PythonAnywhere account

Sign up at https://www.pythonanywhere.com if you haven't already. A free account is fine for development.

#### Step 2 — Open a Bash console

From your PythonAnywhere dashboard, click **Consoles**, then **Bash**.

#### Step 3 — Clone your repository

```bash
git clone https://github.com/YOUR_USERNAME/gnucash-web.git
cd gnucash-web/backend
```

#### Step 4 — Create a virtual environment on PythonAnywhere

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Step 5 — Set up environment variables

```bash
cp .env.example .env
nano .env        # Fill in your values, then Ctrl+O to save, Ctrl+X to exit
```

#### Step 6 — Create a Web App

1. Go to the **Web** tab on your PythonAnywhere dashboard.
2. Click **Add a new web app**.
3. Choose **Manual configuration** (not Flask or Django).
4. Select **Python 3.10**.

#### Step 7 — Configure the WSGI file

PythonAnywhere will show you a path to a WSGI file, something like:

```
/var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py
```

Click that link to edit it. Delete everything in the file and replace it with:

```python
import sys
import os

# Add your project to the path
sys.path.insert(0, '/home/YOUR_USERNAME/gnucash-web/backend')

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv('/home/YOUR_USERNAME/gnucash-web/backend/.env')

# Import the FastAPI app and wrap it for WSGI
from app.main import app as application
```

Replace `YOUR_USERNAME` with your actual PythonAnywhere username.

#### Step 8 — Set the virtual environment path

On the **Web** tab, find the **Virtualenv** section and enter:

```
/home/YOUR_USERNAME/gnucash-web/backend/venv
```

#### Step 9 — Reload and test

Click the green **Reload** button on the Web tab. Then visit:

```
https://YOUR_USERNAME.pythonanywhere.com
```

You should see `{"message": "Hello, World!"}`.

---

## Deploying updates after the first setup

When you have made changes locally and pushed them to GitHub, pull them down on PythonAnywhere like this:

```bash
# In a PythonAnywhere Bash console
cd ~/gnucash-web
git pull
```

Then go to the **Web** tab and click **Reload**. That's it.

If you added new packages to `requirements.txt`, also run:

```bash
cd ~/gnucash-web/backend
source venv/bin/activate
pip install -r requirements.txt
```

---

## Git Workflow (Quick Reference)

If you are new to Git, here are the commands you will use most often.

### Check what has changed

```bash
git status
```

### Stage your changes

```bash
git add .          # Stage everything
# or
git add backend/app/main.py    # Stage a specific file
```

### Commit your changes

```bash
git commit -m "A short description of what you changed"
```

### Push to GitHub

```bash
git push
```

### Pull the latest from GitHub

```bash
git pull
```

---

## Development Phases

- [x] Phase 1: Bare FastAPI scaffold
- [ ] Phase 2: Google OAuth and Drive file I/O
- [ ] Phase 3: Schema design
- [ ] Phase 4: SQLite CRUD on Drive
- [ ] Phase 5: Entities
- [ ] Phase 6: Accounts
- [ ] Phase 7: Transactions and splits
- [ ] Phase 8: Commodities
