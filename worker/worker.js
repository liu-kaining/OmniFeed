/**
 * OmniFeed Cloudflare Worker
 *
 * Handles ticker submission with ETag optimistic locking
 * to prevent concurrent write conflicts.
 */

const TICKER_REGEX = /^[A-Z]{1,5}$/;
const TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const MIN_RETRY_DELAY = 100;
const MAX_RETRY_DELAY = 300;
const MAX_RETRIES = 5;
const RATE_LIMIT_PER_HOUR = 10;

const DEFAULT_ALLOWED_ORIGINS = [
  "https://omnifeed.pages.dev",
  "http://localhost:3000",
  "http://localhost:8080",
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const allowedOrigins = getAllowedOrigins(env);
    const corsHeaders = buildCorsHeaders(origin, allowedOrigins);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    if (url.pathname === "/api/submit-ticker" && request.method === "POST") {
      const allowed = await checkRateLimit(request);
      if (!allowed) {
        return jsonResponse(
          { error: "Rate limit exceeded. Please try again later." },
          429,
          corsHeaders
        );
      }
      return await handleSubmitTicker(request, env, corsHeaders);
    }

    if (url.pathname === "/api/whitelist" && request.method === "GET") {
      return await handleGetWhitelist(env, corsHeaders);
    }

    return new Response("Not Found", { status: 404, headers: corsHeaders });
  },
};

function getAllowedOrigins(env) {
  const extra = (env.ALLOWED_ORIGIN || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return [...DEFAULT_ALLOWED_ORIGINS, ...extra];
}

function buildCorsHeaders(origin, allowedOrigins) {
  const allowOrigin = allowedOrigins.includes(origin)
    ? origin
    : allowedOrigins[0];
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

async function checkRateLimit(request) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const hourBucket = new Date().toISOString().slice(0, 13);
  const cacheKey = new Request(
    `https://rate-limit.omnifeed.internal/${encodeURIComponent(ip)}/${hourBucket}`
  );
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  const count = cached ? Number.parseInt(await cached.text(), 10) || 0 : 0;

  if (count >= RATE_LIMIT_PER_HOUR) {
    return false;
  }

  await cache.put(
    cacheKey,
    new Response(String(count + 1), {
      headers: { "Cache-Control": "max-age=3600" },
    })
  );
  return true;
}

async function handleSubmitTicker(request, env, corsHeaders) {
  try {
    const body = await request.json();
    const { ticker, turnstileToken } = body;

    if (!ticker || typeof ticker !== "string") {
      return jsonResponse({ error: "Ticker symbol is required" }, 400, corsHeaders);
    }

    const sanitizedTicker = ticker.trim().toUpperCase();

    if (
      sanitizedTicker.includes("..") ||
      sanitizedTicker.includes("/") ||
      sanitizedTicker.includes("\\")
    ) {
      return jsonResponse({ error: "Invalid ticker format" }, 400, corsHeaders);
    }

    if (!TICKER_REGEX.test(sanitizedTicker)) {
      return jsonResponse(
        {
          error: "Invalid ticker format. Must be 1-5 uppercase letters (A-Z).",
        },
        400,
        corsHeaders
      );
    }

    if (!env.TURNSTILE_SECRET_KEY) {
      console.error("TURNSTILE_SECRET_KEY not configured");
      return jsonResponse({ error: "Service configuration error" }, 500, corsHeaders);
    }

    if (!turnstileToken) {
      return jsonResponse(
        { error: "Human verification token is required" },
        400,
        corsHeaders
      );
    }

    const turnstileValid = await verifyTurnstile(
      turnstileToken,
      env.TURNSTILE_SECRET_KEY
    );
    if (!turnstileValid) {
      return jsonResponse(
        { error: "Human verification failed. Please try again." },
        403,
        corsHeaders
      );
    }

    const result = await addTickerWithRetry(sanitizedTicker, env);

    if (result.success) {
      return jsonResponse(
        {
          message: `Ticker ${sanitizedTicker} added successfully`,
          ticker: sanitizedTicker,
        },
        200,
        corsHeaders
      );
    }

    if (result.alreadyExists) {
      return jsonResponse(
        {
          message: `Ticker ${sanitizedTicker} is already being monitored`,
          ticker: sanitizedTicker,
        },
        409,
        corsHeaders
      );
    }

    return jsonResponse(
      { error: "Failed to add ticker after multiple attempts. Please try again." },
      500,
      corsHeaders
    );
  } catch (error) {
    console.error("Error in handleSubmitTicker:", error);
    return jsonResponse({ error: "Internal server error" }, 500, corsHeaders);
  }
}

async function addTickerWithRetry(ticker, env) {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const { data, etag } = await getWhitelistWithETag(env);
      const tickers = data.tickers || [];

      if (tickers.includes(ticker)) {
        return { success: false, alreadyExists: true };
      }

      const updatedData = {
        ...data,
        tickers: [...tickers, ticker],
        lastUpdated: new Date().toISOString(),
      };

      const putResult = await putWhitelistWithETag(updatedData, etag, env);
      if (putResult.success) {
        return { success: true, alreadyExists: false };
      }

      if (putResult.conflict) {
        await sleep(
          MIN_RETRY_DELAY + Math.random() * (MAX_RETRY_DELAY - MIN_RETRY_DELAY)
        );
        continue;
      }

      return { success: false, alreadyExists: false };
    } catch (error) {
      console.error(`Attempt ${attempt + 1} failed:`, error);
      if (attempt === MAX_RETRIES - 1) {
        return { success: false, alreadyExists: false };
      }
      await sleep(
        MIN_RETRY_DELAY + Math.random() * (MAX_RETRY_DELAY - MIN_RETRY_DELAY)
      );
    }
  }

  return { success: false, alreadyExists: false };
}

async function getWhitelistWithETag(env) {
  const object = await env.R2_BUCKET.get("config/whitelist.json");

  if (!object) {
    return {
      data: { tickers: [], lastUpdated: new Date().toISOString() },
      etag: null,
    };
  }

  return {
    data: await object.json(),
    etag: object.httpEtag,
  };
}

async function putWhitelistWithETag(data, etag, env) {
  try {
    const options = {
      httpMetadata: {
        contentType: "application/json",
      },
    };

    if (etag) {
      options.onlyIf = { etagMatches: etag };
    }

    const result = await env.R2_BUCKET.put(
      "config/whitelist.json",
      JSON.stringify(data, null, 2),
      options
    );

    if (!result) {
      return { success: false, conflict: true };
    }

    return { success: true, conflict: false };
  } catch (error) {
    console.error("Failed to put whitelist:", error);
    return { success: false, conflict: false };
  }
}

async function handleGetWhitelist(env, corsHeaders) {
  try {
    const object = await env.R2_BUCKET.get("config/whitelist.json");

    if (!object) {
      return jsonResponse({ tickers: [] }, 200, corsHeaders);
    }

    return jsonResponse(await object.json(), 200, corsHeaders);
  } catch (error) {
    console.error("Error getting whitelist:", error);
    return jsonResponse({ error: "Failed to get whitelist" }, 500, corsHeaders);
  }
}

async function verifyTurnstile(token, secretKey) {
  try {
    const response = await fetch(TURNSTILE_VERIFY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        secret: secretKey,
        response: token,
      }),
    });

    const result = await response.json();
    return result.success === true;
  } catch (error) {
    console.error("Turnstile verification failed:", error);
    return false;
  }
}

function jsonResponse(data, status, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
