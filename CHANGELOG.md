# Changelog

## 0.1.0

First release.

- **Preflight** node
  - Post: Validate, Create (draft, scheduled time, local time per channel, queue, publish now with confirmation), Get, Get Many, Update, Delete, Retry.
  - Media: Upload from a public URL or from binary data (single or multipart), waiting until the file is ready; Get; Delete.
  - Channel: Get Many, Get Next Queue Times.
  - Every Create sends an Idempotency-Key.
- **Preflight Trigger** for `post.published` and `post.failed`, registering and removing its own webhook and verifying the timed HMAC signature.
- **Preflight API** credential (API key, optional base URL) with a connection test.
- Five example workflows in `templates/`.
