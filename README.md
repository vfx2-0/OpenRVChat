# OpenRV Google Chat Bot

This repository contains a small Python application that integrates
[OpenRV](https://drive.google.com/file/d/1SFsldpD9mWzKTm9tEKVhW-HwzB8tmC-8/view?usp=sharing)with Google Chat.
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
Example output on Windows:
```
C:\Source\OpenRV\_install\bin>rv -network
INFO: Using 'C:\Users\lever' for $HOME.
rv
Version 2.0.0 (RELEASE), built on Jun  7 2024 at 09:42:59 (HEAD=0ba6a73).
Copyright Contributors to the Open RV Project
INFO: listening on port 45124
INFO: File logger path: C:/Users/lever/AppData/Roaming/ASWF/OpenRV/
INFO: no output plugins found in C:/Users/lever/AppData/Roaming/RV/Output;C:/Source/OpenRV/_install/plugins/Output
```
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
- `PORT` – Port number for the Flask server, used when deploying to Cloud Run or other containers. Defaults to `8080`.

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


## Deploying to Google Workspace Marketplace

A `Dockerfile` and `requirements.txt` are included for running the bot on Google Cloud Run or any platform that can host a Flask application. Build and deploy the container, then configure a Google Chat app in the [Google Workspace Marketplace](https://workspace.google.com/marketplace?host=chat) and set the bot's request URL to `https://YOUR_SERVICE_URL/chat`.

After the app is published, users can install it from the marketplace and open image sequences in OpenRV directly from Google Chat.
