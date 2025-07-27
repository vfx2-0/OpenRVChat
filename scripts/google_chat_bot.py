"""Google Chat bot to upload image sequences to GCS and open them in OpenRV."""

import os
import re
import subprocess
import threading
import time
import datetime
import logging
from pathlib import Path
from typing import Dict, List

from flask import Flask, jsonify, request
from google.cloud import storage
from googleapiclient.discovery import build
import google.auth
from PIL import Image

app = Flask(__name__)
# Flask application used to receive events and serve the upload form

logging.basicConfig(level=logging.INFO)

PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8080")
# Base URL for the web server used in generated links
# Optional Cloud Storage bucket for uploads
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET")
# Restrict uploads to users from this domain if set
ALLOWED_DOMAIN = os.environ.get("ALLOWED_DOMAIN")

GCS_URL_RE = re.compile(r"^gs://([^/]+)/(.+)$")

# Basic instructions sent when the bot is first added to a space.
OPENRV_INSTRUCTIONS = (
    "Download OpenRV from the releases page:\n"
    "<https://github.com/AcademySoftwareFoundation/OpenRV/releases>\n"
    "Then mention @OpenRV Bot in any chat to upload or view sequences."
)

# Extract bucket and object path from a gs:// URL

def _parse_gcs_url(url: str):
    match = GCS_URL_RE.match(url)
    if not match:
        raise ValueError(f"Invalid GCS URL: {url}")
    return match.group(1), match.group(2)

# Retrieve the list of available Google Chat spaces

def _list_spaces() -> List[Dict[str, str]]:
    """Return available Google Chat spaces."""
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/chat.bot"])
    service = build("chat", "v1", credentials=creds, cache_discovery=False)
    resp = service.spaces().list().execute()
    spaces = resp.get("spaces", [])
    return [
        {"name": s.get("name"), "displayName": s.get("displayName", s.get("name"))}
        for s in spaces
    ]

# Send a plain text message to a Google Chat space

def _post_message(space: str, text: str) -> Dict:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/chat.bot"])
    service = build("chat", "v1", credentials=creds, cache_discovery=False)
    return (
        service.spaces().messages().create(parent=space, body={"text": text}).execute()
    )


def _patch_message(name: str, text: str = None, card: Dict | None = None) -> None:
    """Update an existing message with new text or card."""
# Edit an existing message to show progress or results
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/chat.bot"])
    service = build("chat", "v1", credentials=creds, cache_discovery=False)
    body: Dict[str, object] = {}
    mask_parts: List[str] = []
    if text is not None:
        body["text"] = text
        mask_parts.append("text")
    if card is not None:
        body.update(card)
        mask_parts.append("cards")
    if not mask_parts:
        return
    service.spaces().messages().patch(
        name=name, updateMask=",".join(mask_parts), body=body
# Download all files under the given gs:// prefix to a local directory
    ).execute()


def _download_sequence(gcs_url: str, download_dir: Path) -> List[Path]:
    """Download an image sequence from Google Cloud Storage."""
    bucket_name, prefix = _parse_gcs_url(gcs_url)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    download_dir.mkdir(parents=True, exist_ok=True)
    blobs = bucket.list_blobs(prefix=prefix)
    paths: List[Path] = []
    for blob in blobs:
        dest = download_dir / Path(blob.name).name
        blob.download_to_filename(dest.as_posix())
        paths.append(dest)
# Grab the middle frame from a sequence for thumbnail generation
    return sorted(paths)


def _download_middle_frame(gcs_url: str, dest: Path) -> Path:
    """Download the middle frame of the sequence."""
    bucket_name, prefix = _parse_gcs_url(gcs_url)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = sorted(list(bucket.list_blobs(prefix=prefix)), key=lambda b: b.name)
    if not blobs:
        raise FileNotFoundError(f"No files found for {gcs_url}")
    blob = blobs[len(blobs) // 2]
    dest.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(dest.as_posix())
    return dest


# Create a small preview image from a frame
def _create_thumbnail(image_path: Path, thumb_path: Path) -> Path:
    """Create a 512x512 thumbnail. Supports common formats and EXR."""
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(image_path) as img:
            img.thumbnail((512, 512))
            img.save(thumb_path)
        return thumb_path
    except Exception:
        logging.debug("Pillow failed, trying imageio for %s", image_path)
        # Pillow may not support EXR; fall back to imageio if available.
        try:
            import imageio
            import numpy as np

            arr = imageio.imread(image_path.as_posix())
            if arr.dtype != "uint8":
                arr = (arr / arr.max() * 255).astype("uint8")
            img = Image.fromarray(arr)
            img.thumbnail((512, 512))
            img.save(thumb_path)
            return thumb_path
        except Exception as exc:
            logging.error("Failed to create thumbnail: %s", exc)
            raise RuntimeError(f"Failed to create thumbnail: {exc}") from exc

# Store the thumbnail in Cloud Storage and generate a temporary URL

def _upload_thumbnail(bucket_name: str, thumb_path: Path) -> str:
    """Upload a thumbnail to the given bucket and return a signed URL."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"thumbs/{thumb_path.name}")
    blob.upload_from_filename(thumb_path.as_posix())
    return blob.generate_signed_url(expiration=datetime.timedelta(minutes=30))


# Build a Google Chat card with thumbnails and action buttons
def _upload_complete_card(urls: List[str], user: str) -> Dict:
    workspace = Path("/tmp/upload_thumbs")
    widgets = []
    for gcs_url in urls[:20]:
        frame_path = workspace / Path(gcs_url).name
        thumb_path = workspace / f"{Path(gcs_url).stem}.png"
        try:
            _download_middle_frame(gcs_url, frame_path)
            _create_thumbnail(frame_path, thumb_path)
            bucket_name, _ = _parse_gcs_url(gcs_url)
            signed_url = _upload_thumbnail(bucket_name, thumb_path)
            image_widget = {
                "image": {
                    "imageUrl": signed_url,
                    "altText": Path(gcs_url).name,
                }
            }
        except Exception as exc:
            logging.error("Failed to create thumbnail for %s: %s", gcs_url, exc)
            image_widget = {"textParagraph": {"text": Path(gcs_url).name}}
        widgets.extend(
            [
                image_widget,
                {
                    "textButton": {
                        "text": "Open in RV",
                        "onClick": {
                            "action": {
                                "function": "open_rv",
                                "parameters": [{"key": "gcs_url", "value": gcs_url}],
                            }
                        },
                    }
                },
            ]
        )

    widgets.append(
        {
            "textButton": {
                "text": "Open all in RV",
                "onClick": {
                    "action": {
                        "function": "open_rv_all",
                        "parameters": [{"key": "urls", "value": ",".join(urls)}],
                    }
                },
            }
        }
    )
    widgets.append(
        {
            "textButton": {
                "text": "Upload a Sequence",
                "onClick": {"openLink": {"url": f"{PUBLIC_URL}/upload_form"}},
            }
        }
    )

    return {
        "text": f"{len(urls)} image sequence has been uploaded by {user}",
        "cards": [{"sections": [{"widgets": widgets}]}],
    }


@app.route("/upload_form")
# Serve a simple HTML form for uploading sequences
def upload_form():
    spaces = _list_spaces()
    options = "".join(
        f"<option value='{s['name']}'>{s['displayName']}</option>" for s in spaces
    )
    return (
        "<html><body><h1>Upload Sequence</h1>"
        "<form action='/upload' method='post' enctype='multipart/form-data'>"
        "<input type='file' name='files' multiple/><br/>"
        f"Post message to: <select name='space'>{options}</select><br/>"
        "<input type='submit' value='Upload'/></form></body></html>"
    )


@app.route("/upload", methods=["POST"])
# Handle sequence files uploaded from the form
def upload():
    files = request.files.getlist("files")
    target_space = request.form.get("space")
    user_email = request.headers.get("X-Goog-Authenticated-User-Email", "")
    domain = user_email.split("@")[-1] if "@" in user_email else ""
    if ALLOWED_DOMAIN and domain != ALLOWED_DOMAIN:
        logging.warning("Upload attempt from unauthorized domain: %s", domain)
        return "Unauthorized", 403
    if not user_email:
        return "Authentication required", 401
    bucket_name = UPLOAD_BUCKET or f"openrv-{domain.replace('.', '-')}"
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    if not bucket.exists():
        bucket = client.create_bucket(bucket_name)

    count = len(files)
    user = request.headers.get("X-Goog-Authenticated-User-Email", "unknown")
    gcs_urls: List[str] = []

    start = time.time()
    next_update = 60.0
    progress_msg = None
    progress_name = None
    if target_space:
        progress_msg = _post_message(
            target_space, f"Uploading {count} files. ETA {count} min"
        )
        progress_name = progress_msg.get("name")

    for idx, f in enumerate(files):
        blob_name = Path(f.filename).name
        blob = bucket.blob(blob_name)
        blob.upload_from_file(f)
        gcs_urls.append(f"gs://{bucket_name}/{blob_name}")
        elapsed = time.time() - start
        if target_space and progress_name and elapsed > next_update:
            remaining = max(count - idx - 1, 0)
            _patch_message(
                progress_name,
                text=f"Upload in progress… approximately {remaining} min remaining",
            )
            next_update += 60.0

    if target_space and progress_name:
        try:
            card = _upload_complete_card(gcs_urls, user)
            _patch_message(progress_name, card=card)
        except Exception as exc:
            logging.error("Failed to build completion card: %s", exc)
            _patch_message(progress_name, text="Upload complete but failed to generate card")

    return "Upload successful"


# Push the sequence to an existing RV session via rvpush
def _launch_openrv(sequence_dir: Path):
    """Launch the image sequence in an existing RV session via ``rvpush``.

    This assumes ``rv`` is running with networking enabled (``rv -network``).
    ``rvpush`` will send a play command so RV loads the sequence without
    blocking this bot process.
    """

    seq_pattern = str(sequence_dir / "*.exr")
    subprocess.Popen(["rvpush", "-play", seq_pattern])


# Process text messages sent to the bot
def _handle_message(event: Dict) -> Dict:
    event_type = event.get("type")
    if event_type == "ADDED_TO_SPACE":
        return {"text": OPENRV_INSTRUCTIONS}

    text = event.get("message", {}).get("text", "")
    annotations = event.get("message", {}).get("annotations", [])
    url_match = re.search(r"gs://\S+", text)
    if not url_match:
        if annotations:
            return {
                "cards": [
                    {
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": "Upload your image sequences."
                                        }
                                    },
                                    {
                                        "textButton": {
                                            "text": "Upload a Sequence",
                                            "onClick": {
                                                "openLink": {
                                                    "url": f"{PUBLIC_URL}/upload_form"
                                                }
                                            },
                                        }
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }

        return {
            "text": "Please provide a gs:// URL or mention the bot for an upload form."
        }

    gcs_url = url_match.group(0)
    workspace = Path("/tmp/openrv_seq")
    middle_frame = workspace / "middle_frame"
    thumb_path = workspace / "thumbnail.png"
    try:
        _download_middle_frame(gcs_url, middle_frame)
        _create_thumbnail(middle_frame, thumb_path)
        bucket_name, _ = _parse_gcs_url(gcs_url)
        signed_url = _upload_thumbnail(bucket_name, thumb_path)
    except Exception as exc:
        logging.error("Thumbnail generation failed for %s: %s", gcs_url, exc)
        return {"text": f"Failed to create thumbnail: {exc}"}

    card = {
        "cards": [
            {
                "sections": [
                    {
                        "widgets": [
                            {
                                "image": {
                                    "imageUrl": signed_url,
                                    "altText": "Sequence Thumbnail",
                                }
                            },
                            {
                                "textButton": {
                                    "text": "Open in RV",
                                    "onClick": {
                                        "action": {
                                            "function": "open_rv",
                                            "parameters": [
                                                {
                                                    "key": "gcs_url",
                                                    "value": gcs_url,
                                                }
                                            ],
                                        }
                                    },
                                }
                            },
                            {
                                "textButton": {
                                    "text": "Upload a Sequence",
                                    "onClick": {
                                        "openLink": {"url": f"{PUBLIC_URL}/upload_form"}
                                    },
                                }
                            },
                        ]
                    }
                ]
            }
        ]
    }
    return card


# Respond to button clicks from interactive cards
def _handle_card_click(event: Dict) -> Dict:
    function = event.get("common", {}).get("invokedFunction")
    params = {
        p.get("key"): p.get("value")
        for p in event.get("common", {}).get("parameters", [])
    }

    workspace = Path("/tmp/openrv_seq")

    if function == "open_rv":
        gcs_url = params.get("gcs_url")
        if not gcs_url:
            return {"text": "Missing gs:// URL."}
        try:
            _download_sequence(gcs_url, workspace)
        except Exception as exc:
            logging.error("Download failed for %s: %s", gcs_url, exc)
            return {"text": f"Failed to download: {exc}"}
        _launch_openrv(workspace)
        return {"text": "Sequence opened in OpenRV."}

    if function == "open_rv_all":
        urls = params.get("urls", "")
        for url in urls.split(","):
            try:
                _download_sequence(url, workspace)
            except Exception as exc:
                logging.error("Download failed for %s: %s", url, exc)
                continue
        _launch_openrv(workspace)
        return {"text": "Sequences opened in OpenRV."}

    return {"text": "Unknown action."}


@app.route("/chat", methods=["POST"])
# Flask route that receives messages and card clicks from Google Chat
def chat():
    data = request.json or {}
    event_type = data.get("type", "MESSAGE")
    if event_type == "CARD_CLICKED":
        resp = _handle_card_click(data)
    else:
        resp = _handle_message(data)
    return jsonify(**resp), 200


# Run the Flask development server when executed directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
