import assert from "node:assert/strict";
import { test } from "node:test";
import worker, { normalizePhone, twilioSignature } from "../src/worker.js";

const baseEnv = {
  BUSINESS_NAME: "Acme Plumbing",
  TRADE: "plumbing",
  SERVICE_AREA: "Springfield",
  OWNER_PHONE: "+15550000001",
  TWILIO_NUMBER: "+15550000002",
  TWILIO_ACCOUNT_SID: "AC123",
  TWILIO_AUTH_TOKEN: "secret",
  API_KEY: "k",
  REVIEW_LINK: "https://g.page/r/example/review",
  ANTHROPIC_API_KEY: "sk-test",
};

function mockFetch(handlers) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    for (const [match, fn] of handlers) if (String(url).includes(match)) return fn(url, init);
    throw new Error("unexpected fetch " + url);
  };
  return calls;
}
const twilioOk = ["api.twilio.com", () => new Response(JSON.stringify({ sid: "SM1" }), { status: 201 })];

test("normalizePhone", () => {
  assert.equal(normalizePhone("(555) 123-4567"), "+15551234567");
  assert.equal(normalizePhone("1-555-123-4567"), "+15551234567");
  assert.equal(normalizePhone("+447700900123"), "+447700900123");
  assert.equal(normalizePhone("123"), null);
});

test("twilio signature matches Twilio's documented example", async () => {
  // Example from Twilio security docs
  const sig = await twilioSignature(
    "12345",
    "https://mycompany.com/myapp.php?foo=1&bar=2",
    { CallSid: "CA1234567890ABCDE", Caller: "+12349013030", Digits: "1234", From: "+12349013030", To: "+18005551212" }
  );
  assert.equal(sig, "0/KCTR6DLpKmkAf8muzZqo1nDgQ=");
});

test("voice rejects missing signature", async () => {
  const req = new Request("https://w.dev/voice", { method: "POST", body: new URLSearchParams({ From: "+1555" }) });
  const res = await worker.fetch(req, baseEnv);
  assert.equal(res.status, 403);
});

test("voice forwards call with valid signature", async () => {
  const params = { From: "+15551112222", To: "+15550000002" };
  const url = "https://w.dev/voice";
  const sig = await twilioSignature(baseEnv.TWILIO_AUTH_TOKEN, url, params);
  const req = new Request(url, { method: "POST", headers: { "X-Twilio-Signature": sig }, body: new URLSearchParams(params) });
  const res = await worker.fetch(req, baseEnv);
  const body = await res.text();
  assert.equal(res.status, 200);
  assert.match(body, /<Dial timeout="20" action="https:\/\/w.dev\/voice\/status"/);
  assert.match(body, /\+15550000001<\/Dial>/);
});

test("missed call texts caller and owner", async () => {
  const calls = mockFetch([twilioOk]);
  const params = { From: "+15551112222", DialCallStatus: "no-answer" };
  const url = "https://w.dev/voice/status";
  const sig = await twilioSignature(baseEnv.TWILIO_AUTH_TOKEN, url, params);
  const res = await worker.fetch(
    new Request(url, { method: "POST", headers: { "X-Twilio-Signature": sig }, body: new URLSearchParams(params) }),
    baseEnv
  );
  assert.equal(res.status, 200);
  assert.equal(calls.length, 2);
  const first = new URLSearchParams(calls[0].init.body);
  assert.equal(first.get("To"), "+15551112222");
  assert.match(first.get("Body"), /Acme Plumbing/);
});

test("answered call sends nothing", async () => {
  const calls = mockFetch([twilioOk]);
  const params = { From: "+15551112222", DialCallStatus: "completed" };
  const url = "https://w.dev/voice/status";
  const sig = await twilioSignature(baseEnv.TWILIO_AUTH_TOKEN, url, params);
  await worker.fetch(
    new Request(url, { method: "POST", headers: { "X-Twilio-Signature": sig }, body: new URLSearchParams(params) }),
    baseEnv
  );
  assert.equal(calls.length, 0);
});

test("lead: requires auth", async () => {
  const res = await worker.fetch(new Request("https://w.dev/lead", { method: "POST", body: "{}" }), baseEnv);
  assert.equal(res.status, 401);
});

test("lead: AI reply sent to lead, alert to owner", async () => {
  const calls = mockFetch([
    ["api.anthropic.com", () => new Response(JSON.stringify({ content: [{ type: "text", text: "Hi Sam, sorry about the leak!" }] }))],
    twilioOk,
  ]);
  const res = await worker.fetch(
    new Request("https://w.dev/lead", {
      method: "POST",
      headers: { Authorization: "Bearer k", "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Sam", phone: "555-111-2222", message: "Water heater leaking" }),
    }),
    baseEnv
  );
  const data = await res.json();
  assert.equal(data.ok, true);
  assert.equal(data.reply, "Hi Sam, sorry about the leak!");
  assert.equal(calls.length, 3);
  assert.equal(new URLSearchParams(calls[1].init.body).get("To"), "+15551112222");
  assert.equal(new URLSearchParams(calls[2].init.body).get("To"), "+15550000001");
});

test("lead: falls back if Claude fails", async () => {
  mockFetch([["api.anthropic.com", () => new Response("err", { status: 500 })], twilioOk]);
  const res = await worker.fetch(
    new Request("https://w.dev/lead", {
      method: "POST",
      headers: { Authorization: "Bearer k", "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Sam", phone: "5551112222", message: "help" }),
    }),
    baseEnv
  );
  const data = await res.json();
  assert.match(data.reply, /thanks for contacting Acme Plumbing/);
});

test("review request", async () => {
  const calls = mockFetch([twilioOk]);
  const res = await worker.fetch(
    new Request("https://w.dev/review", {
      method: "POST",
      headers: { Authorization: "Bearer k", "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Pat", phone: "5553334444" }),
    }),
    baseEnv
  );
  assert.equal(res.status, 200);
  assert.match(new URLSearchParams(calls[0].init.body).get("Body"), /g\.page\/r\/example\/review/);
});
