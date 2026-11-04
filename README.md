# Ghanjah

AI travel consultant for travel agencies.

Ghanjah is a multi-tenant SaaS platform for travel agencies. Each agency gets its own branded
customer page and messaging channels where an AI consultant answers questions, recommends the
agency's packages and prepares bookings, and a staff dashboard where the agency's team manages
packages, conversations and bookings.

**Tech stack:** Python (FastAPI, SQLAlchemy), PostgreSQL, React + TypeScript (Vite), Docker.

## Running locally

Requirements: Docker with the Compose plugin.

```bash
cp .env.example .env    # then edit the values
docker compose up -d --build
```

The application is then available at <http://localhost:8080>.

For development without Docker (Python 3.12+, Node 20+), run each part in its own terminal:

```bash
# API on http://localhost:8000
cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload

# Web application on http://localhost:5173
cd frontend && npm install && npm run dev
```

## Deployment

See [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
