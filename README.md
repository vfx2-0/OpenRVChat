# OpenRV Google Chat Bot

This repository contains a small Python application that integrates
[OpenRV](https://github.com/AcademySoftwareFoundation/OpenRV) with Google Chat.
The bot allows you to upload image sequences to Google Cloud Storage (GCS)
and quickly open them in OpenRV from a chat room.

## Features

* Upload image sequences from a simple web form or by mentioning the bot in
  Google Chat.
* Automatically generate thumbnails for uploaded sequences.
* Open a sequence or multiple sequences directly in a running OpenRV session
  using `rvpush`.

## Requirements

* Python 3.9 or newer.
* Access to Google Cloud with permission to use Google Chat and Cloud Storage.
* The `rv` application must be running with networking enabled (`rv -network`).
* The following Python packages:
  `flask`, `google-cloud-storage`, `google-api-python-client`, `google-auth`,
  and `Pillow`.

Install packages with:

```bash
pip install flask google-cloud-storage google-api-python-client google-auth pillow
```

## Configuration

The bot uses a few environment variables:

- `PUBLIC_URL` – Base URL where the bot's web server is reachable. Defaults to
  `http://localhost:8080`.
- `UPLOAD_BUCKET` – Optional name of the GCS bucket used for uploads. If not
  provided, a bucket is created based on the requesting domain.

Make sure the service account running the bot has access to the bucket and to
Google Chat APIs.

## Running

Start the bot with:

```bash
python scripts/google_chat_bot.py
```

The Flask server listens on port 8080 by default. See the `PUBLIC_URL`
environment variable if the server is exposed through a different hostname or
port.

## Uploading and Viewing Sequences

1. Add the bot to a Google Chat space.
2. Mention `@OpenRV Bot` in the chat to receive the upload form link.
3. Upload one or more image sequence files.
4. Once uploaded, the bot posts thumbnails with buttons to open each sequence in
   OpenRV. Clicking *Open in RV* downloads the sequence locally and sends a
   command to an existing `rv` process via `rvpush`.

## Development

The source code is located in `scripts/google_chat_bot.py`. The application is a
standard Flask app with a single `/chat` endpoint for Google Chat events and an
upload form served from `/upload_form`.

Feel free to modify or extend the bot to fit your workflow.

