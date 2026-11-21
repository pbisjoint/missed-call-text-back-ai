# Home-Service Lead Automation

Three automations for HVAC, plumbing, roofing and electrical businesses, running on one Cloudflare Worker per client:

| Feature | Trigger | What happens |
|---|---|---|
| Missed-call text-back | Customer calls the client's Twilio number | Call rings the owner's phone. If no one answers, the caller gets a text within seconds and the owner gets an alert. |
| Instant AI lead reply | Website form submits to `/lead` | Claude writes a short, personal SMS reply to the lead. The owner gets the lead details. If Claude is down, a safe template is sent instead. |
| Review request | Owner/CRM posts to `/review` after a job | Customer gets a text with the Google review link. |

Running cost per client is roughly the Twilio number plus SMS fees, plus a few cents of Claude usage. Cloudflare's free Workers tier covers typical small-business volume.

## Setup per client (about 30–45 minutes)

1. **Twilio:** buy a local number. In the US, complete A2P 10DLC registration before texting (required by carriers; approval can take days).
2. **Copy config:** edit `wrangler.toml` (`name`, business details, phone numbers, review link).
3. **Secrets:**
   ```
   wrangler secret put TWILIO_AUTH_TOKEN
   wrangler secret put ANTHROPIC_API_KEY
   wrangler secret put API_KEY
   ```
4. **Deploy:** `npx wrangler deploy` → note the URL, e.g. `https://leads-acme-plumbing.<you>.workers.dev`.
5. **Point Twilio:** number → Voice → "A call comes in" → Webhook `POST https://<worker>/voice`.
6. **Website form:** set the form's webhook to `POST https://<worker>/lead?key=<API_KEY>` with fields `name`, `phone`, `message` (JSON or form-encoded). Works with Jotform, Typeform, Wix, WordPress (WPForms/Gravity), Zapier.
7. **Reviews:** after each job, `POST /review?key=<API_KEY>` with `name`, `phone`, triggered from a Zapier step, the CRM, or a bookmarked form for the owner.
8. **Test:** call the number and let it ring out, then submit the form. Check `GET /health`.

## Testing

```
npm test
```
The 10 tests cover phone normalization, Twilio signature checks (verified against Twilio's documented example), call forwarding, missed-call texts, answered calls, lead auth, the AI reply with fallback, and review requests.

## Want it set up for you?

I can deploy and configure this for your business, usually within 3 days: Twilio number, text-back, AI lead replies and review requests. Open an issue titled **"Setup request"** with your business type and city, and I'll reply with a fixed quote.

## Compliance notes

- Text only people who contacted the business (callers, form submitters) or customers who agreed to it. Put "you may receive texts about your request" on the form.
- Honour STOP replies. Twilio handles STOP/HELP keywords automatically on standard numbers.
- The AI prompt forbids quoting prices or promising arrival times.
