# ☕ Coffee Billing & POS System

A responsive, self-hosted coffee shop billing and sales management web application built with **Python Flask + SQLite**. Designed for small cafés, tea stalls, coffee counters and vending machine operators. **Currency: INR (₹)**.

## Features

- Password-protected administrator login and password change
- Point-of-sale screen with search, product selection, quantity controls and checkout
- Product management (add, edit, hide/enable)
- Configurable GST, rupee discounts, Cash / UPI / Card payments
- Numbered receipts with printable 80 mm layout and browser Save as PDF
- Sales history, customer search, CSV export
- Daily revenue and best-selling products reports
- Responsive layout for mobile and desktop
- Persistent SQLite database, CSRF checks, password hashing

**Scope:** This is a manually operated POS, **not** an integration with a physical coffee machine, card terminal, payment gateway, GST e-invoicing API, or cloud printer. Payments are recorded, not collected. Receipt printing uses the browser's print dialog. The application has a single administrator role.

## Quick start (Windows / macOS / Linux)

Install Python 3.10+ and run:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create environment variables before starting. You can copy `.env.example` to `.env` as a reference, **but Flask does not automatically load `.env` in this project**. Export the variables in your shell or use a process manager / hosting dashboard.

Linux/macOS:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='choose-a-long-unique-password'
python app.py
```

Windows PowerShell:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:ADMIN_USERNAME = 'admin'
$env:ADMIN_PASSWORD = 'choose-a-long-unique-password'
python app.py
```

Open **http://127.0.0.1:5000** and log in. The app automatically initializes the database and demo menu. If `ADMIN_PASSWORD` is not supplied on first run, a random password is printed to the server logs; save it before restarting. Changing environment passwords after the database exists does not change the stored login—use **Account** to change the password.

## How to use

1. Sign in as administrator.
2. In **Settings**, set café name, address, phone, GSTIN (if applicable), and GST rate.
3. In **Products**, edit the demo menu and prices or add products.
4. On **POS**, select products, set quantities, optionally enter customer/discount, select payment method and click **Generate bill**.
5. On the receipt screen click **Print / Save PDF**.
6. View previous invoices in **Bills**; download sales as CSV or review **Reports**.

## Upload to GitHub

1. Create a new **empty** GitHub repository, e.g. `coffee-billing-system`.
2. Extract this ZIP and open a terminal in its `coffee-billing-system` folder.
3. Run:

```bash
git init
git add .
git commit -m "Initial coffee billing POS application"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/coffee-billing-system.git
git push -u origin main
```

Do not upload the `data/` folder, SQLite databases, `.env`, secrets, or customer sales data. The `.gitignore` excludes these.

## Deploy online (Render example)

> **Important:** SQLite must use a persistent disk. Render persistent disks may require a paid plan and have service-specific limitations. **GitHub only stores code; it does not host a live Flask application.** Free or ephemeral deployments can lose bills and settings after restarts/redeploys. Check your hosting provider's current pricing and persistent storage policy.

1. Push your project to GitHub.
2. In Render, choose **New → Blueprint**, connect the repository, and use the included `render.yaml`.
3. Enter a strong `ADMIN_PASSWORD` when prompted. The blueprint generates `SECRET_KEY`.
4. Verify the persistent disk is attached at `/var/data`, with `DATABASE_PATH=/var/data/coffee.db`.
5. Deploy and open the HTTPS URL Render gives you.
6. Log in and **change your password** in Account. Confirm a test bill survives a restart.

The included `render.yaml` runs one Gunicorn worker and configures HTTPS session cookies and trusted proxy headers. For other hosting platforms, use `gunicorn --workers 1 --bind 0.0.0.0:$PORT app:app`, configure environment variables, and mount persistent storage. For higher-volume multi-worker use, migrate from SQLite to a managed database with proper concurrency controls.

## Operations, maintenance & backups

- Back up the **SQLite database** (`DATABASE_PATH`) regularly, preferably using SQLite's online backup API or a database-safe snapshot. Test restoration periodically.
- Keep dependencies and server patched; use HTTPS and a strong admin password.
- Restrict admin access and keep the service private if it contains customer information.
- Monitor `/health`, service logs, disk capacity and backups.
- GitHub stores source-code history, **not your production database**. Never commit customer data.
- Set the correct local timezone (`TZ=Asia/Kolkata` for India) on your host if supported; receipts use the server's local time.
- GST compliance, HSN/SAC, sequential invoice rules, cancellation/refunds, and tax invoice requirements vary. Confirm legal requirements before using for statutory invoicing.

## Limitations / roadmap

Single admin; no refunds, inventory tracking, kitchen tickets, printer hardware integration, email/SMS, offline-first sync, payment collection or multiple shop branches. Daily reports reflect the server timezone. Amounts are stored in paise; historical bills retain the product name and price at sale time. This starter system is suitable for a small trusted admin operation, not a substitute for a full audited enterprise POS.

## Security note

For public production use, add rate limiting for login, authentication monitoring, a production-grade secret manager, periodic backup automation, and any compliance features required by your jurisdiction. Avoid public demo credentials. CSRF tokens protect state-changing routes; server-side billing always recalculates prices from the database.

## Tech stack

Python, Flask, Werkzeug, SQLite, HTML, CSS, vanilla JavaScript, Gunicorn.

## License

MIT — see [LICENSE](LICENSE).
