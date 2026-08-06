# nginx routing on prod — which URL comes from which root

Written 2026-08-06 after publishing a corrected pricing page to a root that
nothing routed to. The config lives at `/etc/nginx/conf.d/domains.conf` on the
box and is **not** in this repo, so this file is the map. `scripts/deploy.sh`
publishes to all three roots; it cannot tell you which URLs each one serves.

## Three static roots, one hostname

`sooppiy.com` is served by host nginx (systemd, not a container). It proxies
`/api` and `/ws` to the backend on `:8101` and serves everything else from disk.

| Root | Serves | Published by |
|---|---|---|
| `/usr/share/nginx/sooppiy` | the SPA — everything not listed below | `deploy.sh`, from the image's `service/frontend/dist` |
| `/usr/share/nginx/sooppiy-marketing` | the Astro pages, see the location list below | `deploy.sh`, from `marketing/dist` |
| `~/sooppiy/admin-site` | `administr.sooppiy.com` (its own `sooppiy-admin` nginx container bind-mounts it) | `deploy.sh`, same dist as the SPA, then `docker restart sooppiy-admin` |

## The marketing root only serves what has a location block

This is the trap. Copying a page into `/usr/share/nginx/sooppiy-marketing` does
nothing on its own — without a matching `location`, the request falls through to
`location /` and gets the SPA shell instead.

Location blocks that route to the marketing root, in config order:

```
/privacypolicy    /termsconditions    /pricing    /smsoptin
/sms-optin-(settings|signup).png      /_astro/
```

Everything else on `sooppiy.com` is the SPA. `marketing/dist/index.html` (the
Astro homepage) is built but deliberately **not** routed — the SPA owns `/`.

Each block is the same shape:

```nginx
location /pricing {
    root /usr/share/nginx/sooppiy-marketing;
    add_header Cache-Control "no-cache";
    try_files $uri $uri/index.html /pricing/index.html;
}
```

Blocks must sit **before** `location /` in the `sooppiy.com` server block.

## Adding a new marketing page

1. Add the page to `marketing/src/pages/`.
2. Add its `location` block on the box, before `location /`.
3. `sudo nginx -t` then `sudo systemctl reload nginx` — never restart, reload.
4. Add it to the publish loop in `scripts/deploy.sh` and to the table above.
5. Verify it serves the real page, not the 457-byte SPA shell:
   `curl -s -o /dev/null -w '%{http_code} %{size_download}\n' https://sooppiy.com/<page>`

Step 5 is the one that catches the mistake this file exists for. A missing
location block still returns **200** — the SPA shell is a valid response. Size
and page title are what distinguish them.

Back up `domains.conf` before editing; the box keeps `domains.conf.bak-*` copies.
