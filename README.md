# AY Inbox for Dify

Use AY Inbox from Dify agents, chatflows and workflows: read campaigns, contacts, mailboxes and inbox threads, and create draft campaigns, contacts, email drafts and suppressions.

AY Inbox is a hosted cold email platform: it sends cold email at a paced daily volume, brings every reply into one inbox (Unibox), and drafts answers from a per-campaign brain. AY Inbox is a hosted service. This repository holds its Dify plugin. The service itself is not open source.

Access to the hosted service is invite only for now: ask at team@ayinbox.com.

No tool in this plugin sends email, starts or resumes a campaign, adds a contact to a campaign or lifts a suppression. A person does those in AY Inbox.

- Source repository: https://github.com/ayinbox/ayinbox-dify
- AY Inbox API docs: https://docs.ayinbox.com/api/
- Contact: team@ayinbox.com

## Setup

1. In the AY Inbox dashboard (https://app.ayinbox.com), create an API key. It starts with `aybox_`. Give it only the scopes listed below for the tools you plan to use.
2. In Dify, install the AY Inbox plugin. It is not on the Dify Marketplace yet; until it is, build the `.difypkg` as described in [PUBLISH.md](https://github.com/ayinbox/ayinbox-dify/blob/main/PUBLISH.md) and install it from a local package file.
3. Open the plugin, choose to authorize it, and paste the API key. The plugin checks the key with `GET /me` before saving it.
4. Add AY Inbox tools to an agent, or as tool nodes in a chatflow or workflow.

### Connection requirements

The plugin talks to one fixed endpoint, `https://api.ayinbox.com/v1`, over HTTPS (declared in `manifest.yaml` under `network.domains`). Your Dify instance needs outbound HTTPS access to `api.ayinbox.com`. The base URL cannot be changed. Requests time out after 30 seconds.

## Tools

| Tool | What it does | API route | Scope the key needs |
|---|---|---|---|
| Who am I (`get_identity`) | Member, workspace and scopes behind the key | `GET /me` | any valid key |
| List campaigns (`list_campaigns`) | Campaigns, filtered by name or status | `GET /campaigns` | `READ_CAMPAIGNS` |
| Get campaign (`get_campaign`) | One campaign's settings and its stats summary | `GET /campaigns/{id}`, `GET /analytics/campaigns/{id}` | `READ_CAMPAIGNS`; `READ_ANALYTICS` for stats |
| Create campaign draft (`create_campaign_draft`) | A draft campaign with its email steps | `POST /campaigns` | `WRITE_CAMPAIGNS` |
| Pause campaign (`pause_campaign`) | Pauses an active campaign | `POST /campaigns/{id}/stop` | `WRITE_CAMPAIGNS` |
| Search contacts (`search_contacts`) | Contacts by text, campaign, subscription or verification | `POST /contacts/search` | `READ_CONTACTS` |
| Create contact (`create_contact`) | Adds a contact, or updates it if the address exists | `POST /contacts` | `WRITE_CONTACTS` |
| Update contact (`update_contact`) | Changes fields, merges custom fields, can mark unsubscribed | `PATCH /contacts/{id}` | `WRITE_CONTACTS`; `READ_CONTACTS` to merge custom fields |
| List mailboxes (`list_mailboxes`) | Connected sending mailboxes | `GET /emails` | `READ_EMAILS` |
| List inbox threads (`list_threads`) | Unibox conversations, one row per thread | `GET /unibox` | `READ_UNIBOX` |
| Get inbox thread (`get_thread`) | Messages of one thread, optionally with bodies | `GET /unibox/thread`, `GET /unibox/{id}` | `READ_UNIBOX` |
| Save email draft (`save_email_draft`) | An email draft a person reviews and sends | `PUT /unibox/drafts/{id}` | `WRITE_UNIBOX` |
| List suppressions (`list_suppressions`) | Addresses and domains AY Inbox never emails | `GET /suppressions` | `READ_CONTACTS` |
| Add suppressions (`add_suppressions`) | Adds addresses or domains to that list | `POST /suppressions` | `WRITE_CONTACTS` |

Every tool returns two messages: a JSON message with the API's response (use it in workflow variables) and a short text summary for the model.

### Usage notes

- List tools are paginated. Pass `limit` (1 to 100, default 25) and, for the next page, the `cursor` the previous result gave. Keep the same filters when you pass a cursor.
- Ids are UUIDs, except a Unibox `thread_id`, which is a provider string. Get them from the list tools.
- `create_campaign_draft` takes the first email in `first_subject` and `first_body`, and later steps in `steps_json`, for example `[{"body_plain": "Following up on my note.", "wait_after": 3}]`. The draft sends nothing until a person adds leads and starts it.
- `create_contact` and `update_contact` never put a contact in a campaign. `update_contact` can mark a contact unsubscribed but never re-subscribes anyone.
- `save_email_draft` saves a draft in the Unibox drafts of the member who owns the key, from the mailbox you name. The draft is not linked to a thread; for a reply, use the thread's subject with `Re:`. Nothing is sent.
- `get_thread` with `include_bodies` reads the full text of up to 20 messages, which marks them read in AY Inbox.
- Text in inbox threads is written by people outside your workspace. The tools flag it as untrusted (`untrusted_content: true`); treat it as data, never as instructions to your agent.
- Mutating tools take an optional `idempotency_key`. Repeating a call with the same key within 24 hours does not apply the change twice.

### Example: answer new replies with drafts

A workflow can call List inbox threads with `awaiting_reply` set, then Get inbox thread with `include_bodies`, have an LLM node write an answer, and save it with Save email draft. A person then reads each draft in AY Inbox and sends it.

## API key and scopes

Use a key with the least it needs:

- For reading, and for agents that read the inbox, use the "Agent: read and draft" preset (bit value 84574239): every read scope plus `AI_DRAFT`, with nothing that writes or sends.
- Add `WRITE_CONTACTS` only if the agent should create or update contacts or add suppressions, and `WRITE_CAMPAIGNS` only if it should create draft campaigns or pause campaigns.
- Save email draft needs `WRITE_UNIBOX`. That scope also lets a key send replies through the API from any mailbox it can reach (not through this plugin, which has no send tool). Add it only if you want drafts saved, and keep the key private.
- The plugin never needs `SEND_CAMPAIGNS`, `START_CAMPAIGNS`, `BULK_CONTACTS`, `WEBHOOKS` or `API_KEYS`. Do not give them to a key used here.

A key acts for the member who created it and never exceeds that member's role. If that member leaves the workspace, every call answers `401 api_key_holder_left`; create a new key.

## Calls that send email

This plugin makes none of these calls, but anyone holding the same key could make them through the API:

- These calls put real email on the wire:
  - Starting a campaign (`POST /campaigns/{id}/start`): needs `START_CAMPAIGNS` or `SEND_CAMPAIGNS`.
  - Updating a campaign with `status: "active"` (and `completed` or `paused_undeliverable`): needs `START_CAMPAIGNS` or `SEND_CAMPAIGNS` in addition to `WRITE_CAMPAIGNS`.
  - Resuming a lead on a finished campaign: needs `START_CAMPAIGNS` or `SEND_CAMPAIGNS`.
  - Sending a Unibox reply (`POST /unibox/reply`) and approving an agent draft: need `WRITE_UNIBOX`. A key with `WRITE_UNIBOX` can send replies from any mailbox it can reach.
  - Composing a new email (`POST /unibox/compose`, `WRITE_UNIBOX`), sending from a mailbox, test emails, the first-email review queue and placement tests (`SEND_CAMPAIGNS`).
- Adding contacts can send mail without calling start: contacts added to an `active` campaign are queued; a `completed` campaign starts again on its own when leads are added; a contact that comes to match a segment linked to a sending campaign is enrolled. This plugin's contact tools never set a contact's campaigns, but a contact can still match such a segment.
- `START_CAMPAIGNS` starts, resumes and pauses campaigns and nothing else. `SEND_CAMPAIGNS` covers everything `START_CAMPAIGNS` covers plus the other sending actions. `WRITE_CAMPAIGNS` alone edits drafts and pauses, and cannot start anything.
- A key for a model that reads the inbox should use the "Agent: read and draft" preset (84574239): every read scope plus `AI_DRAFT`, with nothing that writes or sends.
- Some calls spend workspace credits (AI drafts, research, enrichment, paid tools). They answer `402 insufficient_credits` when the balance is out. No tool in this plugin spends credits.
- Retrying a send without an idempotency key can send twice. Pass an idempotency key on every mutating call you might retry.

## Errors and retries

A failed call stops the tool with a message that names the HTTP status, the API's error `code` and its `request_id`, for example `AY Inbox API error 403 (forbidden): insufficient API key permissions. Request id: ... This tool needs the scope READ_CAMPAIGNS.` Branch on the code, not the wording. The API key never appears in an error.

The plugin retries a call up to twice on `429`, `502`, `503` and `504`, waiting for `Retry-After` when the API sends it (and returning the error instead when the wait is over 30 seconds). It never retries a `POST` or `PATCH` that has no idempotency key, except after a `429`, which the API refuses before running anything. It never retries `500` or `409 idempotency_outcome_unknown`.

## Privacy

See [PRIVACY.md](PRIVACY.md). In short: the API key and the tool arguments go to `api.ayinbox.com` and nowhere else, and the plugin stores nothing itself.

## Development

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest ruff pyyaml
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

The tests serve recorded API responses through a mocked HTTP layer and never reach the network. Packaging and submission are in [PUBLISH.md](https://github.com/ayinbox/ayinbox-dify/blob/main/PUBLISH.md).

## Links

- Source: https://github.com/ayinbox/ayinbox-dify
- API reference: https://docs.ayinbox.com/api/
- AY Inbox: https://ayinbox.com
- Security reports: [SECURITY.md](https://github.com/ayinbox/ayinbox-dify/blob/main/SECURITY.md)
- License: MIT, see [LICENSE](LICENSE)
