# KAIZEN

## Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                            # pon tu OPENAI_API_KEY
```

## Frontend

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

## Contratos

- `backend/core/contracts.py`
- `web/lib/types.ts`, que es su espejo
- `docs/CONTRATOS.md`
