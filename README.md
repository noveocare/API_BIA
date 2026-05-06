# API Data HR — NoveoCare

Django REST API for NoveoCare HR data, using Django 5.2, Django REST Framework, SimpleJWT authentication, and Microsoft SQL Server databases.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Structure](#project-structure)
3. [Environment Configuration (.env)](#environment-configuration-env)
4. [Local Development](#local-development)
5. [Deploy to Azure App Service (HTTPS)](#deploy-to-azure-app-service-https)
6. [HTTPS Configuration in Django](#https-configuration-in-django)
7. [API Documentation](#api-documentation)

---

## Prerequisites

- **Python 3.12+**
- **ODBC Driver 17 for SQL Server** (required by `pyodbc` / `mssql-django`)
- An **Azure account** with access to create App Services and SQL databases
- **Azure CLI** installed (`az`) — [Install guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)

---

## Project Structure

```
├── API/                  # Django app (models, views, permissions, services)
├── API_BIA/               # Django project settings, urls, wsgi/asgi
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── templates/            # HTML templates
├── .env                  # Local environment variables (DO NOT COMMIT)
├── .env.example          # Template for .env (safe to commit)
├── manage.py
├── requirements.txt
└── README.md
```

---

## Environment Configuration (.env)

The application uses **`python-dotenv`** to load configuration from a **`.env`** file at the project root. This file is loaded automatically in `API_HR/settings.py` via `load_dotenv()`.

> ⚠️ **Never commit the `.env` file.** It contains secrets. Make sure `.env` is listed in `.gitignore`.

Copy the template to get started:

```bash
cp .env.example .env
```

### Full `.env` Template

```env
# =============================================================================
# Django Core
# =============================================================================
DJANGO_SECRET_KEY=your-random-secret-key-here
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_HTTPS=False

# =============================================================================
# Default Database (API_DB)
# =============================================================================
API_DB_ENGINE=mssql
API_DB_HOST=your-server.database.windows.net
API_DB_NAME=your_db_name
API_DB_USER=your_db_user
API_DB_PASSWORD=your_db_password
API_DB_PORT=1433
API_DB_DRIVER=ODBC Driver 17 for SQL Server

# =============================================================================
# DBO Database
# =============================================================================
DBO_DB_ENGINE=mssql
DBO_DB_HOST=your-server.database.windows.net
DBO_DB_NAME=your_dbo_db_name
DBO_DB_USER=your_dbo_db_user
DBO_DB_PASSWORD=your_dbo_db_password
DBO_DB_PORT=1433
DBO_DB_DRIVER=ODBC Driver 17 for SQL Server

# =============================================================================
# CAA Database
# =============================================================================
CAA_DB_ENGINE=mssql
CAA_DB_HOST=your-server.database.windows.net
CAA_DB_NAME=your_caa_db_name
CAA_DB_USER=your_caa_db_user
CAA_DB_PASSWORD=your_caa_db_password
CAA_DB_PORT=1433
CAA_DB_DRIVER=ODBC Driver 17 for SQL Server
```

### Variable Reference

| Variable | Description | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key (required) | `""` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated list of allowed hostnames | `localhost,127.0.0.1` |
| `DJANGO_HTTPS` | Enable HTTPS security settings (`True`/`False`) | `False` |
| `API_DB_ENGINE` | Django database engine for default DB | `mssql` |
| `API_DB_HOST` | SQL Server hostname | `""` |
| `API_DB_NAME` | Database name | `""` |
| `API_DB_USER` | Database username | `""` |
| `API_DB_PASSWORD` | Database password | `""` |
| `API_DB_PORT` | Database port | `1433` |
| `API_DB_DRIVER` | ODBC driver name | `ODBC Driver 17 for SQL Server` |
| `DBO_DB_*` | Same pattern as above for the `dbo` database | — |
| `CAA_DB_*` | Same pattern as above for the `caa` database | — |

---

## Local Development

```bash
# 1. Clone the repository
git clone https://github.com/noveocare/api-data-hr.noveocare.com.git
cd api-data-hr.noveocare.com

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file from the template
cp .env.example .env
# Edit .env and fill in your local values

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser (optional, for Django admin)
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

The API will be available at `http://localhost:8000/`.

---

## Deploy to Azure App Service (HTTPS)

### Step 1 — Add Gunicorn to Dependencies

Azure App Service uses **Gunicorn** as the production WSGI server. Add it to `requirements.txt`:

```bash
pip install gunicorn
pip freeze > requirements.txt
```

### Step 2 — Create the Azure Resources

```bash
# Log in
az login

# Create a resource group
az group create --name rg-noveocare-hr --location westeurope

# Create an App Service Plan (Linux, B1 tier minimum)
az appservice plan create \
  --name plan-noveocare-hr \
  --resource-group rg-noveocare-hr \
  --is-linux \
  --sku B1

# Create the Web App (Python 3.12)
az webapp create \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --plan plan-noveocare-hr \
  --runtime "PYTHON:3.12"
```

### Step 3 — Configure Environment Variables on Azure

On Azure, environment variables are set as **Application Settings** (they behave like `.env` but are managed by the platform). Set all the same variables from your `.env`:

```bash
az webapp config appsettings set \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --settings \
    DJANGO_SECRET_KEY="<your-production-secret-key>" \
    DJANGO_ALLOWED_HOSTS="api-data-hr-noveocare.azurewebsites.net,api-data-hr.noveocare.com" \
    DJANGO_HTTPS="True" \
    API_DB_ENGINE="mssql" \
    API_DB_HOST="<your-sql-server>.database.windows.net" \
    API_DB_NAME="<your-db-name>" \
    API_DB_USER="<your-db-user>" \
    API_DB_PASSWORD="<your-db-password>" \
    API_DB_PORT="1433" \
    API_DB_DRIVER="ODBC Driver 17 for SQL Server"
```

> Repeat for `DBO_DB_*` and `CAA_DB_*` variables as needed.

> **Note:** You do **not** deploy a `.env` file to Azure. Application Settings replace it in production.

### Step 4 — Configure the Startup Command

```bash
az webapp config set \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --startup-file "gunicorn API_HR.wsgi:application --bind 0.0.0.0:8000"
```

### Step 5 — Deploy the Code

**Option A — Deploy directly with Azure CLI:**

```bash
az webapp up \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --runtime "PYTHON:3.12"
```

**Option B — Deploy via GitHub Actions (recommended):**

1. In the Azure Portal, go to your App Service → **Deployment Center**.
2. Select **GitHub** as the source and link this repository (`noveocare/api-data-hr.noveocare.com`).
3. Azure will auto-generate a GitHub Actions workflow that builds and deploys on every push to `master`.

### Step 6 — Run Migrations on Azure

```bash
# Open an SSH session to the container
az webapp ssh --name api-data-hr-noveocare --resource-group rg-noveocare-hr

# Inside the container:
cd /home/site/wwwroot
python manage.py migrate
python manage.py collectstatic --noinput
```

### Step 7 — Enable HTTPS-Only

Force all HTTP traffic to redirect to HTTPS:

```bash
az webapp update \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --set httpsOnly=true
```

Azure provides a **free SSL/TLS certificate** for the default `*.azurewebsites.net` domain automatically.

#### Custom Domain with SSL (e.g., `api-data-hr.noveocare.com`)

```bash
# 1. Add the custom domain
az webapp config hostname add \
  --webapp-name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --hostname api-data-hr.noveocare.com

# 2. Create a free managed certificate
az webapp config ssl create \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --hostname api-data-hr.noveocare.com

# 3. Bind the certificate to the hostname
az webapp config ssl bind \
  --name api-data-hr-noveocare \
  --resource-group rg-noveocare-hr \
  --certificate-thumbprint <thumbprint-from-previous-command> \
  --ssl-type SNI
```

---

## HTTPS Configuration in Django

The HTTPS security settings in `API_HR/settings.py` are controlled by the `DJANGO_HTTPS` environment variable in your `.env` file (or Azure Application Settings).

Add the following block at the end of `API_HR/settings.py` (replacing the commented-out HTTPS section):

```python
# HTTPS — controlled by DJANGO_HTTPS in .env
if os.environ.get("DJANGO_HTTPS", "False") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
```

| Setting | Purpose |
|---|---|
| `SECURE_PROXY_SSL_HEADER` | Trusts Azure's `X-Forwarded-Proto` header (required because Azure terminates TLS at the load balancer) |
| `SECURE_SSL_REDIRECT` | Redirects all HTTP requests to HTTPS |
| `SESSION_COOKIE_SECURE` | Session cookies are only sent over HTTPS |
| `CSRF_COOKIE_SECURE` | CSRF cookies are only sent over HTTPS |
| `SECURE_HSTS_*` | Enables HTTP Strict Transport Security (tells browsers to always use HTTPS) |

### Usage

- **Local development:** Set `DJANGO_HTTPS=False` in your `.env` → no HTTPS enforcement.
- **Production (Azure):** Set `DJANGO_HTTPS=True` in Application Settings → full HTTPS enforcement.

---

## API Documentation

Once the application is running, interactive API documentation is available via **Swagger UI** (powered by `drf-yasg`):

| Endpoint | Description |
|---|---|
| `/swagger/` | Swagger UI — interactive API explorer |
| `/redoc/` | ReDoc — alternative API documentation |

### Authentication

The API uses **JWT tokens** via SimpleJWT:

1. Obtain a token pair: `POST /api/token/` with `username` and `password`.
2. Use the access token in subsequent requests: `Authorization: Bearer <access_token>`.
3. Refresh the token: `POST /api/token/refresh/` with the `refresh` token.

---
