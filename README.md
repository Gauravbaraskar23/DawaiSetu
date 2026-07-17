# DawaiSetu

**DawaiSetu** is a full-stack medical marketplace platform built with Django that connects customers with local pharmacies. Sellers manage their medicine inventory, staff, and subscription plans through a dedicated dashboard, while customers browse, order, and track medicines from verified pharmacy partners.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

DawaiSetu is designed as a two-sided marketplace:

- **Customers** browse medicines across verified pharmacies, add to cart, place orders, chat with sellers, and track order status in real time.
- **Sellers (Pharmacies)** get a full inventory management dashboard, subscription-based feature unlocks (custom store links, analytics, staff accounts, bulk export), and tools to run their business efficiently.

The platform is built to scale from a single-owner pharmacy to a multi-staff operation with role-based permissions.

---

## Features

### For Customers
- Browse and search medicines by name, molecule, manufacturer, and category
- Shopping cart with real-time quantity updates
- Order placement, tracking, and cancellation
- In-app chat with sellers per order
- Order history with invoice download
- Email notifications and password reset via secure email flow

### For Sellers
- Full inventory management (add, edit, delete, bulk upload via Excel/CSV)
- **Multi-plan subscription system** — sellers can hold multiple active plans simultaneously, with features combining automatically
- **Staff sub-accounts** with role-based permissions (Order Manager, Inventory Manager, Full Access) — up to the limit allowed by their plan
- Custom store links and custom subdomain support (plan-gated)
- FSSAI license verification with admin approval workflow
- **Store Analytics dashboard** — monthly and yearly visitor trends, orders, sales graphs, and a 5-year performance history with automatic best-year detection
- Bulk order/sales export to Excel for accounting and GST purposes
- Low-stock alerts and inventory valuation (plan-gated)
- Premium "Top 6" homepage placement add-on with slot-limited availability
- Automated subscription expiry reminders and staff account auto-deactivation on plan downgrade

### Platform-Wide
- Real-time in-app notification system with read/unread tracking
- Automated email delivery via SMTP (password reset, order confirmations, support tickets)
- Razorpay payment gateway integration for subscription purchases
- Role-based access control across every view (customer / seller / staff / admin)
- Comprehensive automated test suite covering permissions, subscriptions, and business logic

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django (Python) |
| Database | MySQL |
| Frontend | Django Templates, Tailwind CSS |
| Payments | Razorpay |
| Email | Gmail SMTP |
| Charts | Chart.js |
| Data Processing | Pandas, OpenPyXL |
| Testing | Django TestCase |

---

## Project Structure

```
meditrack/
├── accounts/           # Custom user model, auth, signup/login
├── store/               # Medicines, inventory, seller dashboard, staff management, analytics
├── orders/              # Cart, orders, chat, invoices, profile
├── subscriptions/        # Plans, checkout, payments, pricing
├── notifications/        # In-app notification system
├── templates/            # Shared templates (base, registration)
├── static/                # Static assets
└── meditrack/             # Project settings, root URLs
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- MySQL Server
- A Gmail account with an App Password (for email)
- A Razorpay account (for payments)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/meditrack.git
   cd meditrack
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**

   Copy `.env.example` to `.env` and fill in your own values:
   ```bash
   copy .env.example .env        # Windows
   cp .env.example .env          # macOS/Linux
   ```
   See [Environment Variables](#environment-variables) below for details on each key.

5. **Create the MySQL database**
   ```sql
   CREATE DATABASE meditrack;
   ```

6. **Run migrations**
   ```bash
   python manage.py migrate
   ```

7. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```

   Visit `http://127.0.0.1:8000` in your browser.

---

## Environment Variables

This project uses [`python-decouple`](https://pypi.org/project/python-decouple/) to keep secrets out of source control. Create a `.env` file in the project root with the following keys:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django's cryptographic secret key |
| `DEBUG` | `True` for development, `False` in production |
| `DB_NAME` | MySQL database name |
| `DB_USER` | MySQL username |
| `DB_PASSWORD` | MySQL password |
| `DB_HOST` | Database host (default: `localhost`) |
| `DB_PORT` | Database port (default: `3306`) |
| `EMAIL_HOST_USER` | Gmail address used to send transactional emails |
| `EMAIL_HOST_PASSWORD` | Gmail App Password (not your regular Gmail password) |
| `RAZORPAY_KEY_ID` | Razorpay API key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay API key secret |

> **Never commit your `.env` file.** It is already excluded via `.gitignore`. Use `.env.example` as a reference template for required keys only.

---

## Running Tests

The project includes an automated test suite covering signup/login, staff permissions, multi-plan subscriptions, order management, inventory limits, email delivery, and scheduled management commands.

```bash
python manage.py test
```

To check test coverage:
```bash
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html   # generates a browsable HTML report in htmlcov/
```

---

## Roadmap

- [ ] WhatsApp order notifications via Twilio Business API
- [ ] Production deployment on AWS
- [ ] Razorpay live-mode activation post KYC
- [ ] Automated scheduled tasks via cron (expiry reminders, staff sync)

---

## License

This project is proprietary and not currently licensed for public redistribution. All rights reserved.

---

## Contact

For support or inquiries, reach out at **meditracksupportcontact@gmail.com**.