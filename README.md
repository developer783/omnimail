# OmniMail - Multi-User Email Aggregation Dashboard

A multi-account email aggregation dashboard built with **React + Vite**, **Python FastAPI**, **PostgreSQL**, and **Google OAuth 2.0 (Gmail API)**. Deploy-ready on **Render**.

---

## Features
- 🔐 **Shared-Credentials Auth Gate**: Single login screen protecting access. Generates 30+ day persistent JWT.
- 📬 **Google OAuth 2.0 Multi-Account Integration**: Link unlimited Gmail accounts using authorization code flow with `https://www.googleapis.com/auth/gmail.readonly`.
- 🔄 **Silent Token Renewal**: Uses stored `refresh_token` to renew expired access tokens automatically.
- ⚡ **Indefinite Storage & Scheduled Syncing**: Syncs emails every 5 minutes in background via APScheduler + instant manual trigger.
- 🎨 **HTML Email iframe Sandbox**: Displays raw original HTML email body (formatting, CSS, tables) safely rendered in a sandboxed `srcdoc` iframe.
- 🔒 **Token Encryption at Rest**: Encrypts stored OAuth tokens using Fernet symmetric encryption key from environment.

---

## 🛠️ Google Cloud Console Setup Guide

Before connecting Gmail accounts to OmniMail, set up your Google Cloud OAuth credentials:

### Step 1: Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top bar and click **New Project**.
3. Name your project (e.g., `OmniMail-Aggregator`) and click **Create**.

### Step 2: Enable the Gmail API
1. In the left sidebar, navigate to **APIs & Services** > **Library**.
2. Search for **Gmail API**.
3. Click on **Gmail API** and click **Enable**.

### Step 3: Configure the OAuth Consent Screen
1. Navigate to **APIs & Services** > **OAuth consent screen**.
2. Select **External** user type and click **Create**.
3. Fill in mandatory fields:
   - **App name**: `OmniMail Aggregator`
   - **User support email**: Your email
   - **Developer contact information**: Your email
4. Click **Save and Continue**.
5. On the **Scopes** page:
   - Click **Add or Remove Scopes**.
   - Search for `https://www.googleapis.com/auth/gmail.readonly` and check the box.
   - Click **Update** and then **Save and Continue**.
6. On the **Test Users** page (*Crucial step!*):
   - Click **+ Add Users**.
   - Enter all Google email accounts that you plan to connect to the dashboard.
   - *Note*: Testing mode allows up to 100 test users without needing official Google app verification.
7. Save and complete consent screen setup.

### Step 4: Create OAuth 2.0 Credentials
1. Navigate to **APIs & Services** > **Credentials**.
2. Click **+ Create Credentials** > **OAuth client ID**.
3. Select **Web application** as the Application type.
4. Set **Name** to `OmniMail Web Client`.
5. Under **Authorized redirect URIs**, add:
   - Local development: `http://localhost:8000/auth/google/callback`
   - Production (Render): `https://omnimail-backend.onrender.com/auth/google/callback`
6. Click **Create**.
7. Copy your **Client ID** and **Client Secret**.

---

## 🚀 Local Development Setup

### Prerequisites
- Python 3.10+
- Node.js v18+ and npm

### 1. Configure Environment Variables
Create a `.env` file in the `backend/` directory:
```env
ENV=development
SHARED_USERNAME=admin
SHARED_PASSWORD=admin123
JWT_SECRET=super-secret-jwt-key-change-this-in-production
TOKEN_ENCRYPTION_KEY=   # Auto-generated if left empty

DATABASE_URL=sqlite:///./email_tool.db

GOOGLE_CLIENT_ID=your_client_id_from_google_console
GOOGLE_CLIENT_SECRET=your_client_secret_from_google_console
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

FRONTEND_URL=http://localhost:5173
```

### 2. Start Python FastAPI Backend
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Backend will start on `http://localhost:8000` (API Docs at `http://localhost:8000/docs`).

### 3. Start React + Vite Frontend
In a separate terminal window:
```bash
cd frontend
npm install
npm run dev
```
Frontend app will start on `http://localhost:5173`.

---

## ☁️ Deployment on Render

OmniMail includes a pre-configured [`render.yaml`](file:///c:/Users/Admin/Desktop/email%20tool/render.yaml) blueprint.

### Deployment Steps:
1. Push this repository to GitHub or GitLab.
2. Sign in to [Render](https://render.com/).
3. Click **New +** > **Blueprint**.
4. Connect your repository containing `render.yaml`.
5. Render will automatically detect the blueprint and provision:
   - **omnimail-db** (Free PostgreSQL instance)
   - **omnimail-backend** (Python FastAPI Web Service)
   - **omnimail-frontend** (React Static Site)
6. Supply the required Environment Variables in Render Dashboard when prompted:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `SHARED_PASSWORD`

---

## 🛡️ Security Architecture

1. **Token Encryption at Rest**: All Google `access_token` and `refresh_token` strings are encrypted using Fernet symmetric cryptography prior to database insertion.
2. **Never Expose OAuth Tokens**: API endpoints strip out token data when listing accounts.
3. **HTML Email Iframe Sandboxing**: Email bodies are isolated in `<iframe srcdoc="..." sandbox="allow-popups allow-same-origin allow-scripts"></iframe>` to prevent script execution from compromising host application state while preserving layout and CSS styling.
