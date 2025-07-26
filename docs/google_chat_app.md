# Google Chat OpenRV App

This guide shows how to create a simple Google Chat app named **OpenRV Bot**
that generates a thumbnail from an image sequence stored in Google Cloud Storage
and opens the sequence in OpenRV only when requested.

When **OpenRV Bot** is added to a space for the first time it replies with
instructions to download the prebuilt OpenRV package from the project's
[releases page](https://github.com/AcademySoftwareFoundation/OpenRV/releases).

The initial message response includes only a `512x512` thumbnail and two
buttons: "Open in RV" and "Upload a Sequence". The full sequence is downloaded
and opened after the user clicks the first button. "Upload a Sequence" opens a
simple form that lets the user select local files and upload them to Google
Cloud Storage using their credentials. After the upload succeeds the bot posts a
message back to chat indicating who uploaded the sequence and how many files
were uploaded.

## Overview

1. Google Chat sends an event to your app via HTTP.
2. The app reads the message text and looks for a `gs://` URL.
3. Only the first frame is downloaded from Google Cloud Storage.
4. A `512x512` thumbnail is generated from that frame.
5. The thumbnail and an "Open in RV" button are returned as a card in the chat
   thread.
6. When the user presses the button a second event triggers the download of the
   entire sequence and launches OpenRV.

Google Cloud Storage is recommended for storing image sequences because it
provides high throughput for downloads compared to other Google storage
services.

### Expected message format

The bot watches for a `gs://` URL anywhere in the text of a chat message. The
URL should point at the directory or prefix that contains the sequence files,
for example:

```text
gs://my-bucket/shots/shot01/plate.%04d.exr
```

EXR files are supported when generating thumbnails thanks to the `imageio`
package included in the dependencies.

Only the first matching URL is processed. The bot will download one frame to
create the thumbnail and fetch the rest of the files only if the user chooses to
open the sequence in OpenRV.

### Mentioning the bot

Mention **@OpenRV Bot** in any chat to request an upload. The bot responds with
a card that contains an **Upload a Sequence** button and a drop-down list of
spaces you can post to. Choosing a space and following the button opens the
upload form using your Google credentials.

While your files are uploading the bot posts progress updates every minute with
an estimated time remaining. The same chat card is edited instead of creating
new messages. Once the upload finishes the bot announces the completed upload in
the selected space.

For each uploaded sequence the message includes a thumbnail generated from the
middle frame (up to twenty thumbnails) with an **Open in RV** button underneath.
At the bottom of the card an **Open all in RV** button launches every uploaded
sequence at once followed by the familiar **Upload a Sequence** button and space
selection menu so you can continue posting more sequences.

## Running the app

Install dependencies (the `imageio` package enables EXR thumbnails):

```bash
pip install flask google-cloud-storage Pillow imageio numpy
```

Run the service locally:

```bash
python scripts/google_chat_bot.py
```

Configure a Google Chat bot to send events to the `/chat` endpoint. When a user
posts a message containing a `gs://` URL, the app downloads only the first
frame, creates a thumbnail and returns a card with an "Open in RV" button. When
the button is clicked the full sequence is downloaded and opened in OpenRV.

The card also includes an "Upload a Sequence" button. Clicking it opens a simple
upload page served by the bot. Uploaded files are stored in a Google Cloud
Storage bucket. If the `UPLOAD_BUCKET` environment variable is not set a new
bucket is automatically created for the user's Google domain using the name
`openrv-<domain>`. Set `PUBLIC_URL` to a public base URL for the service so
Google Chat can open the form. The form contains a drop-down menu that lists all
Google Chat spaces the user can post to. After the upload finishes the bot will
post a message of the form `"{n} image sequence has been uploaded by {user}"` to
the selected space. Google credentials are read from the standard
`GOOGLE_APPLICATION_CREDENTIALS` environment variable.

## Domain-wide deployment

If your organization uses Google Workspace you can deploy the bot once for the
entire domain so users do not need to install it individually.

1. Create or select a Google Cloud project and enable the **Google Chat API**
   along with **Cloud Run** and **Cloud Storage**.
2. Deploy `scripts/google_chat_bot.py` to Cloud Run (or another HTTPS hosting
   service) and set `PUBLIC_URL` to the service's base URL. Configure the Chat
   API to send events to `<PUBLIC_URL>/chat`.
3. In the Google Workspace Admin console navigate to **Apps → Google Workspace
   → Chat apps** and add the Chat app from your Cloud project.
4. Choose **Install for everyone** to make the bot accessible in all spaces
   across your domain.
