# OpenRV Google Chat Bot

This repository contains a small Python application that integrates
[OpenRV](https://drive.google.com/file/d/1SFsldpD9mWzKTm9tEKVhW-HwzB8tmC-8/view?usp=sharing)with Google Chat.
The bot allows you to upload image sequences to Google Cloud Storage (GCS)
and quickly open them in OpenRV from a chat room.

## Features

* Upload image sequences from a simple web form or by mentioning the bot in
  Google Chat.
* Automatically generate thumbnails for uploaded sequences using
  time-limited signed URLs so images display correctly in Chat.
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
pip install -r requirements.txt
```

## Configuration

The bot uses a few environment variables:

- `PUBLIC_URL` – Base URL where the bot's web server is reachable. Defaults to
  `http://localhost:8080`.
- `UPLOAD_BUCKET` – Optional name of the GCS bucket used for uploads. If not
  provided, a bucket is created based on the requesting domain.
- `ALLOWED_DOMAIN` – Optional Workspace domain allowed to use the upload form.
  If set, upload requests from other domains are rejected.
- `PORT` – Port number for the Flask server, used when deploying to Cloud Run or other containers. Defaults to `8080`.

Make sure the service account running the bot has access to the bucket and to
Google Chat APIs. Grant it the **Storage Object Admin** role on the bucket and
the **Chat Bot Service Account** role (`roles/chat.bot`). Use this service
account when deploying to Cloud Run.
If `ALLOWED_DOMAIN` is set, the upload form requires users to authenticate with
an email from that domain.

## Running

Start the bot with:

```bash
python scripts/google_chat_bot.py
```

The Flask server listens on port 8080 by default. See the `PUBLIC_URL`
environment variable if the server is exposed through a different hostname or
port.

## Uploading and Viewing Sequences

1. In Google Chat open your space and choose **Add people & bots** to add the bot.
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

## Hosting on Google Cloud Run

The repository includes a `Dockerfile` so the bot can run on Google Cloud Run.
See [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md) for a step-by-step guide to
build the container, deploy it with Cloud Run, and configure the required
environment variables. Once deployed, use the service URL when setting up the
Google Chat application.


## Deploying to Google Workspace Marketplace

To make the bot available from the Google Workspace Marketplace:

1. Follow the steps in [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md) to deploy the container on Cloud Run.
2. Enable the Google Chat API in your project.
3. Create a new Chat app and use the same service account as the Cloud Run service.
4. Set the event endpoint to `https://YOUR_SERVICE_URL/chat`.
5. Publish the app to your domain or publicly.
6. Invite the bot to a space with **Add people & bots**.

After publishing, the bot can be installed from the marketplace and will open uploaded image sequences directly in OpenRV.

