# Frontend

React + Vite + TypeScript dashboard. It consumes only the public Foresight API.

```bash
npm install
npm run generate-client # backend must be running on :8000
npm run dev             # http://localhost:5173
npm run build
```

The generated client is committed so the SPA and API contract change together. Regenerate it
whenever the django-ninja schema changes.
