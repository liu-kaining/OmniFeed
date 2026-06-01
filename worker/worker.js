/**
 * OmniFeed Cloudflare Worker
 *
 * Handles ticker submission with ETag optimistic locking
 * to prevent concurrent write conflicts.
 */

// Input validation regex: 1-5 uppercase letters only
const TICKER_REGEX = /^[A-Z]{1,5}$/;

// Turnstile verification endpoint
const TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

// Random delay range for retry (ms)
const MIN_RETRY_DELAY = 100;
const MAX_RETRY_DELAY = 300;

// Max retry attempts
const MAX_RETRIES = 5;

// Rate limiting: max submissions per IP per hour
const RATE_LIMIT_PER_HOUR = 10;

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
  "https://omnifeed.pages.dev",
  "http://localhost:3000",
  "http://localhost:8080",
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";

    // CORS headers - restrict to allowed origins
    const corsHeaders = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    };

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Route: POST /api/submit-ticker
    if (url.pathname === "/api/submit-ticker" && request.method === "POST") {
      return await handleSubmitTicker(request, env, corsHeaders);
    }

    // Route: GET /api/whitelist
    if (url.pathname === "/api/whitelist" && request.method === "GET") {
      return await handleGetWhitelist(env, corsHeaders);
    }

    return new Response("Not Found", { status: 404, headers: corsHeaders });
  },
};

/**
 * Handle ticker submission with ETag optimistic locking
 */
async function handleSubmitTicker(request, env, corsHeaders) {
  try {
    // Parse request body
    const body = await request.json();
    const { ticker, turnstileToken } = body;

    // Validate ticker format
    if (!ticker || typeof ticker !== "string") {
      return jsonResponse(
        { error: "Ticker symbol is required" },
        400,
        corsHeaders
      );
    }

    // Sanitize: trim whitespace and uppercase
    const sanitizedTicker = ticker.trim().toUpperCase();

    // Additional security: block common injection patterns
    if (sanitizedTicker.includes('..') || sanitizedTicker.includes('/') || sanitizedTicker.includes('\\')) {
      return jsonResponse(
        { error: "Invalid ticker format" },
        400,
        corsHeaders
      );
    }

    // Regex validation: 1-5 uppercase letters only
    if (!TICKER_REGEX.test(sanitizedTicker)) {
      return jsonResponse(
        {
          error: "Invalid ticker format. Must be 1-5 uppercase letters (A-Z).",
        },
        400,
        corsHeaders
      );
    }

    // Verify Turnstile token (required)
    if (!env.TURNSTILE_SECRET_KEY) {
      console.error("TURNSTILE_SECRET_KEY not configured");
      return jsonResponse(
        { error: "Service configuration error" },
        500,
        corsHeaders
      );
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

    // Attempt to add ticker with optimistic locking
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
    } else if (result.alreadyExists) {
      return jsonResponse(
        {
          message: `Ticker ${sanitizedTicker} is already being monitored`,
          ticker: sanitizedTicker,
        },
        409,
        corsHeaders
      );
    } else {
      return jsonResponse(
        { error: "Failed to add ticker after multiple attempts. Please try again." },
        500,
        corsHeaders
      );
    }
  } catch (error) {
    console.error("Error in handleSubmitTicker:", error);
    return jsonResponse(
      { error: "Internal server error" },
      500,
      corsHeaders
    );
  }
}

/**
 * Add ticker with ETag optimistic locking and retry logic
 */
async function addTickerWithRetry(ticker, env) {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      // Step 1: GET whitelist.json and capture ETag
      const { data, etag } = await getWhitelistWithETag(env);

      // Check if ticker already exists
      const tickers = data.tickers || [];
      if (tickers.includes(ticker)) {
        return { success: false, alreadyExists: true };
      }

      // Step 2: Add ticker to array
      const updatedTickers = [...tickers, ticker];
      const updatedData = {
        ...data,
        tickers: updatedTickers,
        lastUpdated: new Date().toISOString(),
      };

      // Step 3: PUT with If-Match ETag
      const putResult = await putWhitelistWithETag(updatedData, etag, env);

      if (putResult.success) {
        return { success: true, alreadyExists: false };
      }

      // ETag mismatch - wait and retry
      if (putResult.conflict) {
        const delay =
          MIN_RETRY_DELAY +
          Math.random() * (MAX_RETRY_DELAY - MIN_RETRY_DELAY);
        await sleep(delay);
        continue;
      }

      // Other error
      return { success: false, alreadyExists: false };
    } catch (error) {
      console.error(`Attempt ${attempt + 1} failed:`, error);
      if (attempt === MAX_RETRIES - 1) {
        return { success: false, alreadyExists: false };
      }
      const delay =
        MIN_RETRY_DELAY +
        Math.random() * (MAX_RETRY_DELAY - MIN_RETRY_DELAY);
      await sleep(delay);
    }
  }

  return { success: false, alreadyExists: false };
}

/**
 * Get whitelist.json from R2 with ETag
 */
async function getWhitelistWithETag(env) {
  const object = await env.R2_BUCKET.get("config/whitelist.json");

  if (!object) {
    // Initialize empty whitelist
    return {
      data: { tickers: [], lastUpdated: new Date().toISOString() },
      etag: null,
    };
  }

  const data = await object.json();
  const etag = object.httpEtag;

  return { data, etag };
}

/**
 * Put whitelist.json to R2 with ETag conditional write
 */
async function putWhitelistWithETag(data, etag, env) {
  try {
    const options = {
      httpMetadata: {
        contentType: "application/json",
      },
    };

    // Add If-Match header if we have an ETag
    if (etag) {
      options.onlyIf = {
        etagMatches: etag,
      };
    }

    const result = await env.R2_BUCKET.put(
      "config/whitelist.json",
      JSON.stringify(data, null, 2),
      options
    );

    if (!result) {
      // ETag mismatch (412 Precondition Failed)
      return { success: false, conflict: true };
    }

    return { success: true, conflict: false };
  } catch (error) {
    console.error("Failed to put whitelist:", error);
    return { success: false, conflict: false };
  }
}

/**
 * Get current whitelist
 */
async function handleGetWhitelist(env, corsHeaders) {
  try {
    const object = await env.R2_BUCKET.get("config/whitelist.json");

    if (!object) {
      return jsonResponse({ tickers: [] }, 200, corsHeaders);
    }

    const data = await object.json();
    return jsonResponse(data, 200, corsHeaders);
  } catch (error) {
    console.error("Error getting whitelist:", error);
    return jsonResponse(
      { error: "Failed to get whitelist" },
      500,
      corsHeaders
    );
  }
}

/**
 * Verify Cloudflare Turnstile token
 */
async function verifyTurnstile(token, secretKey) {
  try {
    const response = await fetch(TURNSTILE_VERIFY_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
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

/**
 * Helper: JSON response
 */
function jsonResponse(data, status, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });
}

/**
 * Helper: Sleep
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
