# Security

## Reporting a problem

Send a description and steps to reproduce to CONTACT_TO_BE_FILLED_IN. Do not open a public issue for a security problem.

## Running it

- `VINNY_TOKEN_SECRET` signs the scoped tokens the web app holds. Without it the engine signs with a built-in dev secret. Set it anywhere outside local development.
- The engine refuses dev tokens on any request that does not come from loopback.
- Connector secrets stay server-side. The web app only ever holds a scoped, short-lived token.
