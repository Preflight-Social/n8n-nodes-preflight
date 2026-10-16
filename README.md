# n8n-nodes-preflight

n8n nodes for [Preflight](https://preflight.social), the social media scheduler that checks every post against each network's real publishing rules before it goes out.

Use it to validate, schedule, queue or publish posts to **YouTube, TikTok, Instagram, Facebook, Threads, LinkedIn, Pinterest, Bluesky, Mastodon, Telegram, Discord and Tumblr** from any n8n workflow, and to react when a post is published or fails.

[n8n](https://n8n.io/) is a [fair-code licensed](https://docs.n8n.io/sustainable-use-license/) workflow automation platform.

- [Installation](#installation)
- [Credentials](#credentials)
- [Operations](#operations)
- [Trigger](#trigger)
- [Example workflows](#example-workflows)
- [Usage notes](#usage-notes)
- [Compatibility](#compatibility)
- [Resources](#resources)
- [Version history](#version-history)

## Installation

Follow the [installation guide](https://docs.n8n.io/integrations/community-nodes/installation/) in the n8n community nodes documentation and install `n8n-nodes-preflight`.

The package has no runtime dependencies.

## Credentials

1. Sign in to [Preflight](https://preflight.social) (every plan, Free included, has API access) and connect your social accounts there. Accounts are connected in the Preflight app, not through the API.
2. Go to **Settings → API keys** and create a key. Give it the scopes your workflows need:

   | Scope | Needed for |
   | --- | --- |
   | `posts:read` | Channels, Get / Get Many posts, queue times, and the credential test |
   | `posts:write` | Drafts, Update and Delete of drafts |
   | `posts:publish` | Anything that goes live: scheduling, queueing, publishing now, retrying |
   | `media:read`, `media:write` | Media → Upload / Get / Delete |
   | `webhooks:read`, `webhooks:write` | The Preflight Trigger |

3. In n8n, create a **Preflight API** credential and paste the key. Leave **Base URL** as `https://preflight.social` unless you run Preflight somewhere else.

The credential test calls `GET /v1/oauth/accounts`, so the key needs `posts:read` for the test to pass.

## Operations

### Post

| Operation | What it does |
| --- | --- |
| **Validate** | Dry-runs the post against every chosen network: text length counted the network's way, hashtags, mentions, links, number and type of files, video length, frame rate and aspect ratio, required options (TikTok privacy, Pinterest board, YouTube title) and your plan's allowance. Returns `ok`, `errorCount`, `warningCount` and `issues[]`. Turn on **Fail on Errors** to stop the workflow instead. |
| **Create** | Creates a post. **When**: Draft (for a person to review), Scheduled Time, Scheduled Local Time per Channel, Queue (next free slot of each channel's schedule) or Publish Now. Preflight runs the same checks as Validate and refuses a post that would fail. |
| **Get** | One post with its per-network status, links, errors and figures. |
| **Get Many** | Posts, newest first, with status and date filters. |
| **Update** | Text, link, files, time or channels of a post that has not gone out. |
| **Delete** | Deletes a draft or cancels a scheduled post. Anything already published stays on the networks. |
| **Retry** | Sends the post again to the channels where it failed, or to one channel by target ID. |

### Media

| Operation | What it does |
| --- | --- |
| **Upload** | From a **public URL** (Preflight downloads it; nothing passes through n8n) or from **binary data** of a previous node (uploaded straight to storage with signed URLs, multipart for files over 16 MB). By default waits until the file is ready and measured. Returns the media ID to use in a post. |
| **Get** | Status (`ingesting`, `processing`, `ready`, `failed`), size, dimensions, duration and a short-lived preview link. |
| **Delete** | Removes the file from the library. |

### Channel

| Operation | What it does |
| --- | --- |
| **Get Many** | Connected accounts with network, name, time zone, `needsReconnect` and `paused`. |
| **Get Next Queue Times** | When the queue would next post to each channel. |

### Choosing channels

Pick channels from the list, or pass them with an expression as a comma-separated string or an array:

- `bluesky:3f2c9a1e-…`: network and channel ID, as the list returns them
- `mastodon`: just the network name, when the workspace has one channel there

That makes channels easy to keep in a spreadsheet column such as `bluesky, linkedin`.

### Per-network options

**Network Options** has fields for the settings people use most (YouTube title, privacy, tags and Short; TikTok privacy and inbox; Instagram placement; Pinterest board and title; first comment). **Options JSON** takes anything else, keyed by network, and is merged over those fields:

```json
{
  "youtube": { "categoryId": "22", "playlistId": "PL…" },
  "bluesky": { "caption": "A shorter text just for Bluesky" }
}
```

The full list is in Preflight's [network options documentation](https://preflight.social/docs/network-options).

## Trigger

**Preflight Trigger** starts a workflow on:

- `post.failed`: a channel refused the post and Preflight has stopped retrying. Sent once per channel, with `error`, `permanent` and `attempts`.
- `post.published`: the post is live on a channel, with `remoteId` and `remoteUrl`. Sent once per channel.

Activating the workflow registers a webhook in Preflight. Deactivating it removes the webhook. Every delivery is signed (`x-preflight-signature-v2: t=<unix>,v2=<HMAC-SHA256 of "t.body">`). The trigger checks the signature against the secret Preflight returned at registration and refuses anything unsigned, tampered with or older than five minutes.

Output:

```json
{
  "event": "post.failed",
  "deliveryId": "3b9f0c6d-1a2e-4f7b-8c5d-6e4a2b1f9c08",
  "createdAt": "2026-10-16T15:50:00.000Z",
  "postId": "7c1e4b2a-9d3f-4e8a-b6c5-2f0a1d9e3b47",
  "targetId": "5b1e…",
  "platform": "pinterest",
  "error": "Board not found. Choose another board.",
  "permanent": true,
  "attempts": 1
}
```

Preflight only delivers to **public https** addresses. A self-hosted n8n on `localhost` needs `WEBHOOK_URL` (or `N8N_WEBHOOK_URL`) set to a tunnel such as Cloudflare Tunnel or ngrok. `deliveryId` stays the same across retries of one event, so you can deduplicate on it.

## Example workflows

The [`templates`](templates) folder has five ready-to-import workflows. Download the JSON and use **Import from File** in n8n.

| Template | What it does |
| --- | --- |
| [Blog RSS → AI caption → drafts](templates/01-rss-ai-caption-validate-draft.json) | New articles get an AI-written caption, Preflight validates it per network, passing posts become drafts. |
| [Google Sheets content calendar](templates/02-google-sheets-content-calendar.json) | Rows marked `Ready` are validated, scheduled or queued, and written back as `Scheduled` or `Needs fix` with the reason. |
| [One vertical video → Shorts, Reels, TikTok](templates/03-vertical-video-shorts-reels-tiktok.json) | Upload through an n8n form; Preflight checks the video rules for all three and queues it. |
| [Notion database → Preflight](templates/04-notion-database-to-preflight.json) | Same as the sheet, for a Notion content database. |
| [Failed post → Slack / Telegram](templates/05-failed-post-slack-telegram-alert.json) | `post.failed` becomes an alert with the network, the reason, whether a retry can work and a link to the post. |

Each template has a sticky note explaining its setup. They are generated by [`templates/build.py`](templates/build.py); see [`templates/README.md`](templates/README.md).

### A minimal example

Validate first, then save a draft only if every network accepts it:

```
Manual Trigger
  → Preflight (Post → Validate, channels: bluesky, mastodon; text: "Hello from n8n")
  → If ({{ $json.ok }} is true)
      true  → Preflight (Post → Create, When: Draft, same channels and text)
      false → (handle {{ $json.issues }})
```

## Usage notes

- **Idempotency.** Every Create sends an `Idempotency-Key`. The default `{{ $execution.id }}-{{ $itemIndex }}` makes n8n's *Retry on Fail* safe. For content that may be seen twice (RSS items, sheet rows) use something stable, e.g. `{{ 'rss-' + $json.link.hash('sha256') }}`: the same key returns the first post instead of creating a second. The same key with different text is refused.
- **Publish Now needs confirming.** Choosing *Publish Now* also requires **Confirm Publish Now**, so a test run cannot publish by accident.
- **Times.** *Scheduled Time* accepts ISO 8601 with a zone, or a wall-clock time such as `2026-11-02 09:30`, which is read in the workflow's time zone. A time more than five minutes in the past is refused by Preflight (`scheduled_in_past`), so an old item can never go out straight away.
- **Files must be ready.** Upload waits for that by default. If you turn waiting off, check **Media → Get** before creating the post.
- **TikTok** never takes links in the text (Preflight refuses them), and needs a privacy level.
- **Errors** carry Preflight's own code and message (for example `validation_failed` with each issue, or `post_limit` with the plan's allowance), and work with n8n's *Continue On Fail*.
- The action node can be used as a tool by n8n's AI Agent.

## Compatibility

- Tested with n8n 2.43.7 (self-hosted, Node.js 24).
- Built with `@n8n/node-cli` 0.52, `n8nNodesApiVersion` 1, strict mode (n8n Cloud eligible).
- Preflight REST API v1 (`https://preflight.social/v1`). *Get Next Queue Times* uses the same API key against Preflight's MCP endpoint (`/mcp`), because the REST queue endpoint is not yet open to API keys.

## Resources

- [Preflight API documentation](https://preflight.social/documentation)
- [OpenAPI schema](https://preflight.social/openapi.json)
- [Webhooks](https://preflight.social/docs/webhooks) · [Errors](https://preflight.social/docs/errors) · [Network options](https://preflight.social/docs/network-options)
- [n8n community nodes documentation](https://docs.n8n.io/integrations/#community-nodes)
- Support: [GitHub issues](https://github.com/Preflight-Social/n8n-nodes-preflight/issues) or info@preflight.social

## Version history

See [CHANGELOG.md](CHANGELOG.md).

- **0.1.0**: first release. Preflight node (Post, Media, Channel) and Preflight Trigger (`post.published`, `post.failed`).
