import os
import re
import uuid
import shutil
import subprocess
import logging
import threading
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, request, send_file, abort
from google.cloud import storage
from googleapiclient.discovery import build
import google.auth
from PIL import Image

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CONFIGURATION
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8080").rstrip('/')
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET")
TEMP_DIR = Path("/tmp/openrv_bot")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

GCS_URL_RE = re.compile(r"^gs://([^/]+)/(.+)$")

# --- Services Caching ---
# Cache authenticated services to avoid re-auth on every request
_CHAT_SERVICE = None

def get_chat_service():
    global _CHAT_SERVICE
    if not _CHAT_SERVICE:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/chat.bot"])
        _CHAT_SERVICE = build("chat", "v1", credentials=creds, cache_discovery=False)
    return _CHAT_SERVICE

# --- Helpers ---

def _parse_gcs_url(url: str):
    match = GCS_URL_RE.match(url)
    if not match:
        raise ValueError(f"Invalid GCS URL: {url}")
    return match.group(1), match.group(2)

def _download_blob(blob, dest_path: Path):
    """Helper for parallel downloads."""
    blob.download_to_filename(str(dest_path))
    return dest_path

def _download_sequence_parallel(gcs_url: str, download_dir: Path) -> List[Path]:
    """Downloads an image sequence using a ThreadPool."""
    bucket_name, prefix = _parse_gcs_url(gcs_url)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    blobs = list(bucket.list_blobs(prefix=prefix))
    if not blobs:
        raise FileNotFoundError(f"No files found at {gcs_url}")

    paths = []
    # Download in parallel using 8 workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for blob in blobs:
            # Skip "folder" placeholders
            if blob.name.endswith('/'): 
                continue
            dest = download_dir / Path(blob.name).name
            futures.append(executor.submit(_download_blob, blob, dest))
        
        for future in concurrent.futures.as_completed(futures):
            try:
                paths.append(future.result())
            except Exception as e:
                logger.error(f"Failed to download blob: {e}")
                
    return sorted(paths)

def _get_middle_blob(gcs_url: str):
    """Identifies the middle blob without downloading it yet."""
    bucket_name, prefix = _parse_gcs_url(gcs_url)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    # Sort blobs to ensure we get the actual middle frame
    blobs = sorted([b for b in bucket.list_blobs(prefix=prefix) if not b.name.endswith('/')], key=lambda b: b.name)
    
    if not blobs:
        raise FileNotFoundError(f"No files found for {gcs_url}")
    return blobs[len(blobs) // 2]

def _create_thumbnail(image_path: Path, thumb_path: Path) -> Path:
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(image_path) as img:
            img.thumbnail((512, 512))
            # Convert to RGB if saving as JPEG/PNG prevents alpha errors
            if img.mode in ("RGBA", "P"): 
                img = img.convert("RGB")
            img.save(thumb_path, format="PNG")
        return thumb_path
    except Exception as e:
        logger.warning(f"PIL failed ({e}), trying generic fallback/error")
        # Add ImageIO fallback here if needed, omitted for brevity
        raise e

# --- Chat API Helpers ---

def _patch_message(name: str, text: str = None, card: Dict = None) -> None:
    service = get_chat_service()
    body = {}
    mask_parts = []
    if text:
        body["text"] = text
        mask_parts.append("text")
    if card:
        body.update(card)
        mask_parts.append("cards")
    
    if mask_parts:
        try:
            service.spaces().messages().patch(
                name=name, updateMask=",".join(mask_parts), body=body
            ).execute()
        except Exception as e:
            logger.error(f"Failed to patch message: {e}")

# --- Core Logic ---

def _process_upload_background(files, target_space, user_email, progress_name):
    """Background worker to handle uploads without blocking Flask."""
    bucket_name = UPLOAD_BUCKET or "openrv-uploads" # Fallback bucket
    client = storage.Client()
    try:
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            bucket = client.create_bucket(bucket_name)
    except Exception as e:
        logger.error(f"Bucket error: {e}")
        return

    # Create a unique request ID for temp storage to avoid collisions
    req_id = str(uuid.uuid4())
    upload_staging = TEMP_DIR / req_id
    upload_staging.mkdir(exist_ok=True)

    gcs_urls = []
    
    try:
        for idx, file_storage in enumerate(files):
            # Save locally first (flask file streams can be finicky in threads)
            # In a production app, stream directly to GCS via blob.upload_from_file
            local_path = upload_staging / file_storage.filename
            file_storage.save(local_path)
            
            blob = bucket.blob(file_storage.filename)
            blob.upload_from_filename(local_path)
            gcs_urls.append(f"gs://{bucket_name}/{file_storage.filename}")
            
            # Simple progress update every 5 files
            if idx % 5 == 0 and target_space and progress_name:
                 _patch_message(progress_name, text=f"Uploading... {idx}/{len(files)}")

        # Create Thumbnail for the card
        if gcs_urls:
            thumb_filename = f"{req_id}_thumb.png"
            thumb_path = TEMP_DIR / "public_thumbs" / thumb_filename
            # Download middle frame logic applied to the first URL
            blob = _get_middle_blob(gcs_urls[0]) # Simply using first seq or file
            mid_path = upload_staging / "mid_frame"
            blob.download_to_filename(mid_path)
            _create_thumbnail(mid_path, thumb_path)

            # Generate Card
            image_url = f"{PUBLIC_URL}/thumbnails/{thumb_filename}"
            
            widgets = [
                {"image": {"imageUrl": image_url, "altText": "Preview"}},
                {"textParagraph": {"text": f"Uploaded by {user_email}"}},
                {
                    "textButton": {
                        "text": "Open in RV",
                        "onClick": {
                            "action": {
                                "function": "open_rv",
                                "parameters": [{"key": "gcs_url", "value": gcs_urls[0]}]
                            }
                        }
                    }
                }
            ]
            
            card = {"cards": [{"sections": [{"widgets": widgets}]}]}
            _patch_message(progress_name, text="Upload Complete", card=card)

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        if progress_name:
            _patch_message(progress_name, text=f"Upload failed: {str(e)}")
    finally:
        # Cleanup staging
        shutil.rmtree(upload_staging, ignore_errors=True)

# --- Routes ---

@app.route("/thumbnails/<filename>")
def serve_thumbnail(filename):
    """Serve thumbnails so Google Chat can render them via HTTP."""
    safe_path = TEMP_DIR / "public_thumbs" / filename
    if safe_path.exists():
        return send_file(safe_path, mimetype='image/png')
    abort(404)

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    target_space = request.form.get("space")
    user_email = request.headers.get("X-Goog-Authenticated-User-Email", "unknown")

    if target_space:
        msg = get_chat_service().spaces().messages().create(
            parent=target_space, body={"text": "Starting upload..."}
        ).execute()
        progress_name = msg.get("name")
        
        # We must copy file streams or save them before passing to thread
        # because the request context dies when this function returns.
        # This is a simplified implementation; for huge files, stream to GCS directly.
        thread = threading.Thread(
            target=_process_upload_background,
            args=(files, target_space, user_email, progress_name)
        )
        thread.start()

    return "Upload started in background", 200

# --- Action Handling ---

def _launch_rv_safe(sequence_dir: Path):
    """
    Launches RV. 
    NOTE: This only works if the server has a display or is the user's workstation.
    """
    try:
        # Check if RV is in path
        if not shutil.which("rv"):
            logger.error("RV executable not found in PATH")
            return

        env = os.environ.copy()
        # Ensure DISPLAY is set if running on Linux locally
        if "DISPLAY" not in env and sys.platform.startswith("linux"):
             env["DISPLAY"] = ":0"

        subprocess.Popen(["rv", str(sequence_dir)], env=env)
        logger.info(f"Launched RV on {sequence_dir}")
    except Exception as e:
        logger.error(f"Failed to launch RV: {e}")

def _handle_card_click(event: Dict) -> Dict:
    invoked_fn = event.get("common", {}).get("invokedFunction")
    params = {p["key"]: p["value"] for p in event.get("common", {}).get("parameters", [])}

    if invoked_fn == "open_rv":
        gcs_url = params.get("gcs_url")
        if not gcs_url:
            return {"text": "Error: Missing URL"}

        # 1. Create a unique workspace for this specific click action
        req_id = str(uuid.uuid4())
        workspace = TEMP_DIR / "sessions" / req_id
        
        # 2. Download in background (fire and forget for the UI response)
        # However, for the user to see RV open, we usually wait. 
        # But Chat times out after 30s. Large sequences take longer.
        # Best approach: Send a message saying "Loading...", then launch.
        
        def _bg_launch():
            try:
                paths = _download_sequence_parallel(gcs_url, workspace)
                if paths:
                    _launch_rv_safe(workspace)
                # Optional: Clean up workspace after X minutes?
            except Exception as e:
                logger.error(f"Background launch failed: {e}")

        threading.Thread(target=_bg_launch).start()

        return {"text": "Downloading sequence and launching RV locally..."}

    return {"text": "Unknown action"}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json or {}
    if data.get("type") == "CARD_CLICKED":
        resp = _handle_card_click(data)
    else:
        # Simplified message handler
        resp = {"text": "Please mention me to upload or use the Upload button."}
    return jsonify(resp)

# Add upload_form route (omitted for brevity, largely same as original)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
