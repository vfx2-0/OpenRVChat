# Deploying the OpenRV Chat Bot on Google Cloud Run

This guide explains how to build and deploy the chat bot on Google Cloud and connect it to Google Workspace so it can be published in the [Google Workspace Marketplace](https://workspace.google.com/marketplace?host=chat).

## Prerequisites

- A Google Cloud project with billing enabled.
- The `gcloud` command line tool installed and authenticated.
- Permissions to create Cloud Run services, Cloud Storage buckets and Google Chat applications.

## Enable Required APIs

Run the following command once to enable the necessary services:

```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    chat.googleapis.com \
    iamcredentials.googleapis.com
```

## Build the Container Image

From the repository root build the Docker image using Cloud Build and push it to your project:

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/openrv-bot
```
Replace `PROJECT_ID` with your Google Cloud project ID.

## Create a Service Account

Create a service account for the Cloud Run service and grant it the
necessary permissions:

```bash
gcloud iam service-accounts create openrv-bot \
    --display-name "OpenRV Chat Bot"

# Allow access to your upload bucket
gsutil iam ch \
  serviceAccount:openrv-bot@PROJECT_ID.iam.gserviceaccount.com:objectAdmin \
  gs://YOUR_BUCKET

# Allow the bot to call the Google Chat API
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member serviceAccount:openrv-bot@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/chat.bot
```

## Deploy to Cloud Run

Deploy the image to Cloud Run and set the required environment variables:

```bash
gcloud run deploy openrv-bot \
    --image gcr.io/PROJECT_ID/openrv-bot \
    --region REGION \
    --service-account openrv-bot@PROJECT_ID.iam.gserviceaccount.com \
    --allow-unauthenticated \
    --set-env-vars "PUBLIC_URL=https://SERVICE_URL,UPLOAD_BUCKET=YOUR_BUCKET,ALLOWED_DOMAIN=yourdomain.com"
```
- `REGION` is your preferred deployment region, e.g. `us-central1`.
- After deployment the command prints `SERVICE_URL`. Use this value for the `PUBLIC_URL` variable so links in Chat point back to your service.
- `YOUR_BUCKET` is an existing Cloud Storage bucket used to store uploads.
- `openrv-bot@PROJECT_ID.iam.gserviceaccount.com` is the service account email created above.
- `ALLOWED_DOMAIN` restricts uploads to users from your Workspace domain.

## Add the Bot to Google Workspace

1. Navigate to **APIs & Services → Credentials** in the Cloud Console and create a service account if you have not already.
2. Grant the service account the **Storage Object Admin** role on the bucket and the **Chat Bot Service Account** role (`roles/chat.bot`).
3. Create a Google Chat application in the [Google Workspace Marketplace](https://workspace.google.com/marketplace?host=chat) using the same service account and configure its event endpoint to `https://SERVICE_URL/chat`.
4. Publish the app to your domain or publicly as needed.
5. In Google Chat open your space and use **Add people & bots** to invite the bot.

Once published, users can install the bot from the marketplace and upload sequences directly from Google Chat.
