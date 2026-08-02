# The Ultimate Django Setup Guide: Industry-Standard Architecture

Welcome to your Django journey! This guide acts as your personal teacher, walking you through everything we did to set up a production-ready, industry-standard Django application. 

Instead of the default setup that works for quick tutorials but fails at scale, this architecture is designed for **maintainability**, **modularity**, and **enterprise-level standards**.

---

## Part 1: The Setup Steps & Commands

Here is a breakdown of the exact commands used to bootstrap this project, what they do, and why we used them.

### 1. Creating the Virtual Environment
```bash
uv venv
```
* **Purpose**: Creates an isolated container (`.venv` folder) for your project's dependencies.
* **Why**: It prevents dependency conflicts between different Python projects on your machine. We used `uv` instead of standard `python -m venv` because `uv` is blindingly fast and modern.

### 2. Activating the Environment
```bash
source .venv/bin/activate
```
* **Purpose**: "Turns on" the virtual environment. Any `python` or `pip` commands you run after this will be isolated to the `.venv` folder.

### 3. Installing Dependencies
```bash
uv pip install django django-environ psycopg2-binary
```
* **Purpose**: Downloads and installs third-party packages.
* **Why these packages?**
  * `django`: The core web framework.
  * `django-environ`: The industry standard for securely reading `.env` files (so you never hardcode secrets like passwords).
  * `psycopg2-binary`: The standard database adapter connecting Django to a PostgreSQL database.

### 4. Scaffolding the Project
```bash
django-admin startproject config .
```
* **Purpose**: Generates the base project files.
* **Why "config ."?** By default, Django names the configuration directory after your project (e.g., `hydr8/hydr8/settings.py`), which is confusing. By using `config .`, we tell Django to name the folder `config` and build it in the current directory (`.`).

### 5. Creating the Modular Directories
```bash
mkdir -p apps requirements templates/partials static
```
* **Purpose**: Creates the folders needed for our scalable architecture.
* **Why**: The default Django setup dumps everything in the root folder. We proactively organize it into distinct, logical categories.

---

## Part 2: The Directory Structure Explained

Below is the layout of your new `server/` directory and exactly what each piece does.

```text
server/
├── apps/                        # Your Business Domains
├── config/                      # The Brain of the Application
│   ├── settings/                
│   │   ├── base.py              
│   │   ├── local.py             
│   │   └── production.py        
│   ├── asgi.py                  
│   ├── wsgi.py                  
│   └── urls.py                  
├── requirements/                # Dependency Management
├── static/                      # Static Assets (CSS/JS)
├── templates/                   # HTML & HTMX Responses
├── .env.local                   # Local Secrets
├── .env.production              # Production Secrets
├── .gitignore                   # Version Control Rules
└── manage.py                    # The Command Center
```

### Deep Dive into the Folders & Files

#### 1. `apps/`
* **Use Case**: This is where you will build your actual features (e.g., `users`, `billing`, `dashboard`). In Django, an "app" is a module that handles a specific business domain.
* **Teacher's Note**: To create a new app, you will navigate into `server/` and run `python manage.py startapp my_app apps/my_app`. This keeps your root folder clean.

#### 2. `config/`
* **Use Case**: The core configuration that controls the entire project. It tells Django what apps are installed, how to connect to the database, and how to route URLs.
* **Inside `settings/`**: 
  * `base.py`: The foundation. Things that are true regardless of where the app is running (e.g., installed apps, middleware).
  * `local.py`: Settings only used on your laptop (e.g., `DEBUG = True`, local database).
  * `production.py`: Settings used on the live server (e.g., security headers, `DEBUG = False`).

#### 3. `manage.py`
* **Use Case**: A command-line utility that lets you interact with this Django project.
* **Teacher's Note**: You will use this constantly. `python manage.py runserver` to start the app, `python manage.py makemigrations` to update the database, etc. We customized it to look at `config.settings.local` by default.

#### 4. `.env` files (`.env.local`, `.env.production`)
* **Use Case**: Securely stores environment variables like `SECRET_KEY`, Database Passwords, and API Keys.
* **Teacher's Note**: These files are NEVER committed to GitHub (thanks to our `.gitignore`). When running locally, you simply copy `.env.local` to `.env` or run the server with those variables loaded.

#### 5. `templates/` & `static/`
* **Use Case**: `templates/` holds your HTML files (and HTMX partials). `static/` holds your CSS, JavaScript, and images.
* **Teacher's Note**: Because you are using **HTMX**, your `templates/partials/` folder will be heavily used. Instead of returning full pages, your Django views will often return small HTML fragments from this folder to swap into the live page.

---

## Part 3: Pro-Tips for Django & HTMX Development

As your teacher, here are the most important rules of thumb to remember as you build:

> [!TIP]
> **1. Fat Models, Skinny Views**
> Never put complex business logic or massive calculations inside `views.py`. Put them inside your `models.py` (if it strictly relates to the data) or create a `services.py` file for complex workflows. Views should only grab data and return a response.

> [!IMPORTANT]
> **2. The N+1 Query Trap**
> Django's ORM is magical but can be slow if abused. Always use `.select_related()` (for ForeignKeys) or `.prefetch_related()` (for Many-to-Many relationships) when querying the database to prevent making hundreds of hidden SQL queries.

> [!NOTE]
> **3. HTMX + Django = Magic**
> In your views, you can detect if a request came from HTMX using `if request.htmx:`. If true, return a small partial HTML template. If false, return the full page template. This is the secret to building Single-Page Applications without React!

> [!WARNING]
> **4. Never Touch Applied Migrations**
> When you change a model, run `makemigrations` and `migrate`. NEVER manually edit a migration file that has already been applied to your database, or you will corrupt your database history.

> [!TIP]
> **5. Always Reactivate**
> Every time you open a new terminal to work on your backend, don't forget to navigate into your `server/` folder and run `source .venv/bin/activate`. If your terminal says `(venv)` or similar, you're good to go!

> [!NOTE]
> **6. Contextualize with Repomix**
> After completing any significant coding task, feature implementation, or architectural change, make sure to execute `npx repomix` inside your `server/` directory. This ensures the entire codebase graph is packed and updated for future contextual needs!

Happy Coding! You have an incredibly robust foundation built here. Take it one app at a time.
