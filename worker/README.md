# Worker secrets — see config/README.md

Setup:

```bash
cd worker
npm install
npx wrangler deploy
npx wrangler secret put TURNSTILE_SECRET_KEY
npx wrangler secret put ALLOWED_ORIGIN   # optional
```

API endpoints documented in the main README.
