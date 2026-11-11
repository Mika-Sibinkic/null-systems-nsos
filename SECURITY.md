# Security

## Reporting a problem

Report it privately through GitHub: the Security tab of this repo, then "Report a vulnerability". Do not open a public issue for a security problem.

## Running it

- `VINNY_TOKEN_SECRET` signs the scoped tokens the web app holds. Without it the engine signs with a built-in dev secret, which is public in `client/onboarding/auth.py`. Set it anywhere outside local development.
- Without `VINNY_TOKEN_SECRET`, the API answers only loopback callers (`127.0.0.1`, `::1`) and returns 404 to everyone else, however it is started. `python -m engine.api` also refuses to listen on anything but loopback in that mode and exits with an error.
- Connector secrets stay server-side. The web app only ever holds a scoped, short-lived token.
