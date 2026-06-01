# OmniFeed Cloudflare Worker

This worker handles the ticker submission endpoint with ETag optimistic locking
to prevent concurrent write conflicts with the GitHub Actions ETL pipeline.

## Setup

1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```

2. Login to Cloudflare:
   ```bash
   wrangler login
   ```

3. Configure environment variables in `wrangler.toml`

4. Deploy:
   ```bash
   wrangler deploy
   ```

## Environment Variables

- `R2_BUCKET`: R2 bucket binding for whitelist storage
- `TURNSTILE_SECRET_KEY`: Cloudflare Turnstile secret key for bot protection

## API Endpoints

### POST /api/submit-ticker

Submit a new ticker symbol to the monitoring whitelist.

**Request Body:**
```json
{
  "ticker": "AMD",
  "turnstileToken": "..."
}
```

**Response:**
- `200 OK`: Ticker added successfully
- `400 Bad Request`: Invalid ticker format
- `409 Conflict`: Ticker already exists
- `412 Precondition Failed`: Write conflict (auto-retry)
- `500 Internal Server Error`: Server error
