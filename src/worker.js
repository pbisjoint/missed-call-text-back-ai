// Home-service lead automation — Cloudflare Worker
// Features:
//  1. Missed-call text-back  (Twilio Voice webhook -> forwards call; if unanswered, texts caller)
//  2. Instant AI lead reply   (website form POST -> Claude drafts reply -> SMS to lead + alert to owner)
//  3. Review requests         (POST after a job is done -> SMS with Google review link)
//
// One deployment per client. All client details live in env vars (see wrangler.toml).

const TWILIO_API = "https://api.twilio.com/2010-04-01";
const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/health") {
        return json({ ok: true, business: env.BUSINESS_NAME });
      }
      if (request.method !== "POST") return new Response("Not found", { status: 404 });

      switch (url.pathname) {
        case "/voice":
          return await handleVoice(request, env);
        case "/voice/status":
          return await handleVoiceStatus(request, env);
        case "/lead":
          return await handleLead(request, env);
        case "/review":
          return await handleReview(request, env);
        default:
          return new Response("Not found", { status: 404 });
      }
    } catch (err) {
      console.error("Unhandled error", err && err.stack ? err.stack : err);
      return new Response("Server error", { status: 500 });
    }
  },
};

// ---------- 1. Missed-call text-back ----------

// Twilio calls this when someone dials the tracking number. We forward to the owner's phone.
async function handleVoice(request, env) {
  const params = await verifiedTwilioParams(request, env);
  if (!params) return new Response("Forbidden", { status: 403 });

  const statusUrl = new URL("/voice/status", request.url).toString();
  const twiml =
    `<?xml version="1.0" encoding="UTF-8"?>` +
    `<Response><Dial timeout="${Number(env.RING_SECONDS || 20)}" action="${xml(statusUrl)}" method="POST">` +
    `${xml(env.OWNER_PHONE)}</Dial></Response>`;
  return new Response(twiml, { headers: { "Content-Type": "text/xml" } });
}

// Twilio calls this after the forwarded call ends. If nobody answered, text the caller.
async function handleVoiceStatus(request, env) {
  const params = await verifiedTwilioParams(request, env);
  if (!params) return new Response("Forbidden", { status: 403 });

  const status = params.DialCallStatus; // completed | busy | no-answer | failed | canceled
  const caller = params.From;
  const empty = `<?xml version="1.0" encoding="UTF-8"?><Response/>`;

  if (status !== "completed" && caller) {
    const msg =
      env.MISSED_CALL_TEXT ||
      `Hi, this is ${env.BUSINESS_NAME}. Sorry we missed your call! We're on a job right now. ` +
        `What can we help with? Reply here and we'll get right back to you.`;
    await sendSms(env, caller, msg);
    await sendSms(env, env.OWNER_PHONE, `Missed call from ${caller}. Auto-text sent.`);
  }
  return new Response(empty, { headers: { "Content-Type": "text/xml" } });
}

// ---------- 2. Instant AI lead reply ----------

async function handleLead(request, env) {
  if (!authorized(request, env)) return new Response("Unauthorized", { status: 401 });

  const lead = await readBody(request);
  const name = clean(lead.name, 80);
  const phone = normalizePhone(lead.phone);
  const message = clean(lead.message, 1000);
  if (!phone) return json({ ok: false, error: "valid phone required" }, 400);

  let reply;
  try {
    reply = await draftReply(env, { name, message });
  } catch (err) {
    console.error("Claude draft failed, using fallback", err);
    reply = null;
  }
  if (!reply) {
    reply = `Hi${name ? " " + name : ""}, thanks for contacting ${env.BUSINESS_NAME}! ` +
      `We got your request and will call you shortly. Reply here with any details or photos.`;
  }

  await sendSms(env, phone, reply);
  await sendSms(
    env,
    env.OWNER_PHONE,
    `New lead: ${name || "(no name)"} ${phone}\n"${message.slice(0, 200)}"\nAuto-reply sent.`
  );
  return json({ ok: true, reply });
}

async function draftReply(env, { name, message }) {
  if (!env.ANTHROPIC_API_KEY) return null;
  const res = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: env.MODEL || "claude-haiku-5-5",
      max_tokens: 200,
      system:
        `You write SMS replies for ${env.BUSINESS_NAME}, a ${env.TRADE || "home service"} company ` +
        `serving ${env.SERVICE_AREA || "the local area"}. Reply in under 300 characters, friendly and ` +
        `professional. Acknowledge the customer's issue, say someone will call shortly, and ask one ` +
        `useful question (address, urgency, or a photo). Never quote prices, never promise times, ` +
        `never give safety-critical advice beyond "if you smell gas or see sparks, call 911". Output only the SMS text.`,
      messages: [
        { role: "user", content: `Customer name: ${name || "unknown"}\nCustomer message: ${message || "(none)"}` },
      ],
    }),
  });
  if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  return text ? text.slice(0, 480) : null;
}

// ---------- 3. Review requests ----------

async function handleReview(request, env) {
  if (!authorized(request, env)) return new Response("Unauthorized", { status: 401 });
  const body = await readBody(request);
  const phone = normalizePhone(body.phone);
  const name = clean(body.name, 80);
  if (!phone) return json({ ok: false, error: "valid phone required" }, 400);
  if (!env.REVIEW_LINK) return json({ ok: false, error: "REVIEW_LINK not configured" }, 500);

  const msg =
    `Hi${name ? " " + name : ""}, thanks for choosing ${env.BUSINESS_NAME}! ` +
    `If we did a great job, a quick review helps a lot: ${env.REVIEW_LINK}`;
  await sendSms(env, phone, msg);
  return json({ ok: true });
}

// ---------- Helpers ----------

export async function sendSms(env, to, body) {
  const auth = btoa(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`);
  const res = await fetch(`${TWILIO_API}/Accounts/${env.TWILIO_ACCOUNT_SID}/Messages.json`, {
    method: "POST",
    headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ To: to, From: env.TWILIO_NUMBER, Body: body }),
  });
  if (!res.ok) throw new Error(`Twilio ${res.status}: ${await res.text()}`);
  return res.json();
}

// Validates X-Twilio-Signature (HMAC-SHA1 of URL + sorted params). Returns params or null.
export async function verifiedTwilioParams(request, env) {
  const form = await request.formData();
  const params = {};
  for (const [k, v] of form.entries()) params[k] = String(v);
  if (env.SKIP_TWILIO_SIGNATURE === "true") return params; // local testing only

  const signature = request.headers.get("X-Twilio-Signature");
  if (!signature) return null;
  const expected = await twilioSignature(env.TWILIO_AUTH_TOKEN, request.url, params);
  return timingSafeEqual(signature, expected) ? params : null;
}

export async function twilioSignature(authToken, url, params) {
  const data = url + Object.keys(params).sort().map((k) => k + params[k]).join("");
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(authToken), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

function authorized(request, env) {
  // Header (preferred) or ?key= for form builders that only support a webhook URL.
  if (!env.API_KEY) return false;
  const h = request.headers.get("Authorization") || "";
  const q = new URL(request.url).searchParams.get("key") || "";
  return timingSafeEqual(h, `Bearer ${env.API_KEY}`) || timingSafeEqual(q, env.API_KEY);
}

async function readBody(request) {
  const type = request.headers.get("Content-Type") || "";
  if (type.includes("application/json")) return (await request.json()) || {};
  const form = await request.formData();
  return Object.fromEntries(form.entries());
}

// US-centric E.164 normalization. Returns "+1XXXXXXXXXX" or null.
export function normalizePhone(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  if (/^\+[1-9]\d{7,14}$/.test(s)) return s;
  const d = s.replace(/\D/g, "");
  if (d.length === 10) return "+1" + d;
  if (d.length === 11 && d.startsWith("1")) return "+" + d;
  return null;
}

function clean(v, max) {
  return String(v || "").replace(/[\u0000-\u001f]/g, " ").trim().slice(0, max);
}

function xml(s) {
  return String(s || "").replace(/[<>&"']/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" }[c]));
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
}
