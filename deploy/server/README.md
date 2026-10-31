# Running StrictDoc as a shared server

This directory runs the StrictDoc web server for a team, with single sign-on
in front of it:

    browser --HTTPS--> Caddy --> oauth2-proxy --> StrictDoc

- Caddy terminates TLS and gets certificates automatically.
- oauth2-proxy signs users in through your OIDC identity provider. A request
  that is not signed in never reaches StrictDoc.
- StrictDoc runs as one process with one worker. It keeps the project model in
  memory, so do not run more than one replica against the same project.

## Setup

1. Clone the StrictDoc project to serve onto the host, for example to
   `/srv/strictdoc/project`. The server reads `strictdoc.toml` from the root of
   that clone if there is one.
2. Register an OIDC client with your identity provider. The redirect URI is
   `https://<your domain>/oauth2/callback`.
3. Copy `.env.example` to `.env` and fill it in. `STRICTDOC_UID` and
   `STRICTDOC_GID` must match the owner of the project clone, because the
   server writes edits back to it.
4. Start the stack:

       cd deploy/server
       docker compose up -d --build

5. Check it:

       docker compose ps                     # strictdoc should be "healthy"
       docker compose logs -f strictdoc

## How it behaves

- Edits made in the web UI are written to the `.sdoc` files in the project
  clone. They are not committed. Commit and push them from the host.
- The server runs with `--watch`, so a `git pull` on the host reloads the
  project in every open browser.
- Generated HTML and caches are kept in the `strictdoc_output` volume, not in
  the project clone.
- Project actions are turned off, because the server does not listen on a
  loopback address. Do not set `allow_remote_project_actions` on this server:
  anyone who can sign in could run the configured commands.
- The StrictDoc container has no internet access. Only oauth2-proxy and Caddy
  can reach the outside.
- StrictDoc identifies the user from oauth2-proxy's `X-Forwarded-Email` and
  `X-Forwarded-Preferred-Username` headers, and shows their initials at the
  bottom of the nav bar. It rejects any request without `X-Forwarded-Email`
  (401, or a closed WebSocket), so it cannot be used anonymously even if the
  proxy is bypassed. Caddy removes these headers from incoming requests so a
  browser cannot set them itself.
- `GET /healthz` returns `{"status": "ok", "version": ...}`. It takes no locks
  and is only reachable from inside the Docker network.

## Not done yet

- StrictDoc knows who is signed in, but does not record it anywhere yet.
  Edits in the files are still anonymous.
- There are no roles. Everyone who can sign in can edit.
- Nothing commits or pushes edits automatically.

## Proxy auth options

The compose file passes these to `strictdoc server`:

| Option                      | Purpose                                  |
|-----------------------------|------------------------------------------|
| `--auth-proxy-user-header`  | Identifies the user. Required on every request. |
| `--auth-proxy-email-header` | The user's email address. Optional.      |
| `--auth-proxy-name-header`  | The user's display name. Optional.       |

The same settings can go in the project's `strictdoc.toml` under `[server]`
as `auth_proxy_user_header`, `auth_proxy_email_header` and
`auth_proxy_name_header`. The command-line options replace all three.
Without them, the server works as before, with no users.

## Updating

    git pull                       # this repository
    docker compose up -d --build strictdoc

## Building the image alone

From the repository root:

    docker build -f deploy/server/Dockerfile -t strictdoc-server .

Build arguments: `INSTALL_CHROME` (default `true`, needed for PDF printing),
`STRICTDOC_UID`, `STRICTDOC_GID` (default `1000`).
