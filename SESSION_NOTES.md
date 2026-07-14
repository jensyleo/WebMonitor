### WebMonitor session - quick notes (v1.0.0)

- Project: EH/WebMonitor/WebMonitor.py

#### Key changes implemented
- Centralized messaging in `MESSAGES` with unified text (OK, 1xx, 3xx, 4xx, 5xx, DNS, SSL, timeout, service unavailable).
- Colors: "Service unavailable" now uses `RGB_BLUE` (0,183,211).
- HTTP logic:
  - 2xx: OK (returns True)
  - 1xx: "Site up with informational response"
  - 3xx: "Site up with redirect"
  - 4xx: "Site up with client response"
  - 5xx: "Site up with server error"
  - Outside 100-599: non-standard status
- `normalize_url`:
  - Now resolves DNS beforehand (`socket.gethostbyname`); if it doesn't resolve → None (classified as DNS error in the main flow).
  - Uses HEAD (1.5s) for quick scheme probing: HTTPS first, then HTTP on failure.
- Main check: GET with a 2.0s timeout.
- Retries: applied on timeout, connection errors, and when no web service is detected; consistent retry messages.
- `urls.txt` filtering: ignores empty/whitespace lines and comments (`#`).
- Removed the flexible message import (no more separate messages file; everything lives in a single script).

#### Reverted decisions (for reference)
- Discarded the 0.3s backoff between retries.
- Reverted the version that normalized without `requests` and alternated schemes per attempt.

#### How to run
- Dependencies: `pip install requests colorama`
- Run: `python3 WebMonitor.py`
- `urls.txt` must be in the same directory as `WebMonitor.py`.

See [TODO.md](TODO.md) for pending work and future improvements.
