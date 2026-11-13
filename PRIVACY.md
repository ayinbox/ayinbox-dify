# Privacy policy for the AY Inbox Dify plugin

This policy covers the AY Inbox plugin for Dify (author `ayinbox`, plugin `ayinbox`). AY Inbox is a hosted cold email platform; the plugin is a client of its REST API.

## What the plugin sends, and where

- The plugin sends requests to one host only: `https://api.ayinbox.com/v1`. It contacts no other service, runs no analytics and sends no telemetry.
- Each request carries the AY Inbox API key you saved in the plugin's credentials, in the `Authorization` header.
- Each request carries the arguments of the tool being run, such as a search text, a campaign id, a contact's name and email address, a draft's recipients, subject and body, or the addresses you ask to suppress.
- When you save the credential, the plugin calls `GET /me` once to check that the key works.

## What the plugin stores

The plugin itself stores nothing. It keeps no files, database, cache or logs of its own, and it writes neither the API key nor tool arguments or results anywhere. The API key is held by your Dify instance as a plugin credential, under Dify's own storage and encryption.

## What comes back

Tool results come from your AY Inbox workspace and can include personal data: contact names, email addresses, company names, phone numbers and the text of email messages. The plugin returns them to Dify, where your workflow, agent or chosen model provider processes them according to your Dify setup. Choose a workspace, an app and a model provider you are allowed to share that data with. Give the API key only the scopes your tools need.

## What AY Inbox does with the data

Data sent to `api.ayinbox.com` is processed by AY Inbox to run your workspace, the same as data you enter in the AY Inbox dashboard. AY Inbox's own privacy policy page is not published yet. Until it is, ask questions about how AY Inbox handles data at team@ayinbox.com.

## Contact

team@ayinbox.com
