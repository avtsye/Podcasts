# Podcasts RSS Monitor

GitHub Actions service for monitoring podcast RSS feeds, downloading new episodes, uploading them to Google Drive, and sending email notifications.

Demo feed: https://www.nasa.gov/feeds/podcasts/houston-we-have-a-podcast

The first run marks current episodes as already seen. Later runs process only new episodes.

Audio is never committed to Git; it is temporary on the Actions runner and uploaded to Drive.

Main files:
- src/monitor.py
- src/drive.py
- src/mailer.py
- src/state.py
- config/podcasts.json
- dashboard/index.html
- .github/workflows/podcast-monitor.yml
- data/state.json

Required GitHub Secrets:
GOOGLE_TOKEN_JSON, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM, MAIL_TO, MAIL_SUBJECT_PREFIX.
