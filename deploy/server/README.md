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
- Roles come from the user's groups (`X-Forwarded-Groups`), set in `.env`:
  - **viewer**: anyone who can sign in. Can read, search and export.
  - **editor**: members of `STRICTDOC_EDITOR_GROUP`. Can also change
    documents and requirements.
  - **admin**: members of `STRICTDOC_ADMIN_GROUP`. Can also edit grammars.

  The server checks the role on every request. In the browser, controls the
  user cannot use are hidden.
- `GET /healthz` returns `{"status": "ok", "version": ...}`. It takes no locks
  and is only reachable from inside the Docker network.

## Not done yet

- StrictDoc knows who is signed in, but does not record it anywhere yet.
  Edits in the files are still anonymous.
- Nothing commits or pushes edits automatically.

## Proxy auth options

The compose file passes these to `strictdoc server`:

| Option                      | Purpose                                  |
|-----------------------------|------------------------------------------|
| `--auth-proxy-user-header`  | Identifies the user. Required on every request. |
| `--auth-proxy-email-header` | The user's email address. Optional.      |
| `--auth-proxy-name-header`  | The user's display name. Optional.       |
| `--auth-proxy-groups-header`| The user's groups, comma-separated.      |
| `--auth-editor-group`       | Group whose members are editors. Repeatable. |
| `--auth-admin-group`        | Group whose members are admins. Repeatable.  |

The same settings can go in the project's `strictdoc.toml` under `[server]`
as `auth_proxy_user_header`, `auth_proxy_email_header`,
`auth_proxy_name_header`, `auth_proxy_groups_header`, and the lists
`auth_editor_groups` and `auth_admin_groups`. The command-line options
override them. `--auth-proxy-user-header` replaces all three user headers.
Without any of them, the server works as before: no users, everyone can edit.

If no editor or admin group is set, every user is a viewer, and the server
logs a warning at startup.

### Checking the groups claim

If an editor can't edit, hover over the initials in the nav bar to see the
role they got. If it says viewer, your provider is probably not sending the
groups claim. Depending on the provider, add `groups` to `OIDC_SCOPE`, add a
groups mapper to the client, or set `OIDC_GROUPS_CLAIM` to the claim your
provider uses. Group names must match exactly, including case. Some
providers (e.g. Microsoft Entra ID) send group IDs instead of names.

## Updating

    git pull                       # this repository
    docker compose up -d --build strictdoc

## The image

The server uses the general StrictDoc image of `deploy/docker`, which also
has Typst and PlantUML, so the web UI's `Export to PDF (Typst)` works here
once the project sets `typst_pdf_command` (see `deploy/docker/README.md`).
The compose file builds it without Chrome, so the server makes PDFs with
Typst. Set `INSTALL_CHROME=true` in `.env` for the HTML2PDF export. `STRICTDOC_UID` and
`STRICTDOC_GID` default to `1000`.
