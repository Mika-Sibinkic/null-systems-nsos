# Security

## Reporting a problem

Email a description and steps to reproduce to mikasibinkic@gmail.com. Do not open a public issue for a security problem.

## Running it

- `VINNY_TOKEN_SECRET` signs the scoped tokens the web app holds. Without it the engine signs with a built-in dev secret. Set it anywhere outside local development.
- Without `VINNY_TOKEN_SECRET`, `python -m engine.api` refuses to listen on anything but loopback (`127.0.0.1`, `localhost`, `::1`) and exits with an error.
- Connector secrets stay server-side. The web app only ever holds a scoped, short-lived token.
