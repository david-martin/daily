# d**ai**ly

A personal daily briefing script. Runs once a day, fetches content from configured
RSS sources, scores and filters items using the Claude API, stores results in SQLite,
and generates static HTML files you can serve however you like.

**Disclaimer: this project uses the Claude API (Anthropic).**

---

## What it does

- Fetches any RSS feed (full article text extracted automatically if not in feed)
- Scores items 1–10 for relevance using a personal profile you define
- Keeps the top N items; discards the rest
- Comics (flagged with `comic: true`) bypass scoring and are included when new
- Writes one HTML file per day plus a browsable index — no web framework required

---

## Requirements

- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com)
- Somewhere to run a daily cron or systemd timer

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/daily
cd daily
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp example.config.yaml config.yaml  # edit to taste
```

Edit `config.yaml` — add your RSS sources and write your scoring profile.

---

## Run

```bash
ANTHROPIC_API_KEY=YOUR_API_KEY python daily.py --config config.yaml
```

HTML files appear in the `output_dir` you configured. Serve that directory with
any static file server, or point Caddy/nginx `root` at it.

---

## Config reference

See `example.config.yaml` for a fully annotated example.

| Field | Description |
|---|---|
| `sources[].name` | Display name shown in the briefing |
| `sources[].url` | RSS feed URL |
| `sources[].comic` | `true` to treat as a comic (skip scoring, link image) |
| `scoring.profile` | Free-text description of you and your interests |
| `scoring.categories` | Priority order for ranking |
| `scoring.top_n` | How many items to keep per day |
| `scoring.min_score` | Minimum score to include (1–10) |
| `output_dir` | Where HTML files are written |
| `model` | Claude model to use for scoring |

---

## Schedule

Any scheduler works. Example systemd timer (7am UTC):

```ini
# /etc/systemd/system/daily-runner.timer
[Timer]
OnCalendar=*-*-* 07:00:00 UTC
Persistent=true
```

```ini
# /etc/systemd/system/daily-runner.service
[Service]
Type=oneshot
ExecStart=/path/to/.venv/bin/python /path/to/daily.py --config /path/to/config.yaml
Environment=ANTHROPIC_API_KEY=YOUR_API_KEY
```
