# Garage
3D driving sim + AI backend. Built by Nikhil Chary Sriramoju.
- Run `sh get-vendor.sh` once to bundle three.js locally (recommended).
- Static only: open `web/index.html` via any static server (`cd web && python3 -m http.server`).
- Full stack: `docker compose up --build` then http://localhost:8000
- Agent + RAG + CNN endpoints: `/api/agent`, `/api/cnn`, `/api/health`.
- Vercel/Netlify serve `web/` only (coach falls back offline). Render runs the Docker image (full backend).
