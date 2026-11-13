# Changelog

## 0.1.0 (unreleased)

- First version of the AY Inbox tool plugin for Dify, with 14 tools: who am I, list campaigns, get campaign (with stats), create campaign draft, pause campaign, search contacts, create contact, update contact, list mailboxes, list inbox threads, get inbox thread, save email draft, list suppressions and add suppressions.
- One API key credential, checked against `GET /me`. The base URL is fixed to `https://api.ayinbox.com/v1`.
- Typed error messages with the API `code` and `request_id`; retries on 429, 502, 503 and 504 that honour `Retry-After` and never repeat a mutation sent without an idempotency key.
- No tool sends mail, starts a campaign or adds a contact to a campaign.
