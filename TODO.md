# TODO

## Pending

- Replace the `LICENSE` file with the verbatim official GPLv3 text
  (currently a partial reconstruction) — easiest via GitHub's license
  template picker when creating/editing the repo.
- General code review pass for further debugging and cleanup.

## Future improvements

- Treat 1xx/3xx as success (`True`) if that behavior is preferred.
- Make timeouts and retry count configurable (config file or env vars).
- Add file/JSON logging with rotation.
- Add concurrency for monitoring large URL lists.
