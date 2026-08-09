This directory is published to https://sooppiy.com/.well-known/ .

Why it exists
-------------
Some providers prove you control a domain by fetching a file from this exact
path. Sign in with Apple is the first: it wants

    https://sooppiy.com/.well-known/apple-developer-domain-association.txt

Files here must live in the repo, not be copied onto the server by hand. Every
deploy replaces the SPA root wholesale, so a hand-placed file disappears on the
next release — and the provider silently marks the domain unverified, with no
error anywhere in our logs.

The trap this file also guards
------------------------------
`cp -r src/*` and `rm -rf dir/*` use a shell glob, and a glob does not match
dotfiles. Before 2026-08-09, scripts/deploy.sh used both, so this entire
directory was dropped on every deploy while the visible site kept working.

This README is the canary. If

    curl -s https://sooppiy.com/.well-known/README.txt

stops returning this text — especially if it returns index.html, which nginx
serves for ANY missing path via `try_files $uri /index.html` — then dotfile
publishing has regressed and any verification file here is already gone.
Check the status code alone and it will lie to you: a missing file still
answers 200.
