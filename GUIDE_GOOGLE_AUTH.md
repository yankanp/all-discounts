# How to Get Google OAuth Credentials

## 1. Create a Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the specific project dropdown in the top bar.
3. Click **New Project**.
4. Name it (e.g., "Coupon Saver") and click **Create**.

## 2. Enable Gmail API
1. In the sidebar, go to **APIs & Services > Library**.
2. Search for **Gmail API**.
3. Click on it and click **Enable**.

## 3. Configure OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**.
2. Choose **External** (for personal use/testing) and click **Create**.
3. Fill in:
   - **App Name**: "Coupon Saver"
   - **User Support Email**: Your email.
   - **Developer Contact Info**: Your email.
4. Click **Save and Continue**.
5. **Scopes**: Click **Add or Remove Scopes**.
   - Search for `gmail.readonly` and select it.
   - Click **Update**, then **Save and Continue**.
6. **Test Users**:
   - Click **Add Users**.
   - Enter your own Gmail address (since the app is in "Testing" mode, only listed users can sign in).
   - Click **Save and Continue**.

## 4. Create Credentials
1. Go to **APIs & Services > Credentials**.
2. Click **+ Create Credentials** (top bar) > **OAuth client ID**.
3. **Application Type**: Select **Web application**.
4. **Name**: "Coupon App Local".
5. **Authorized Redirect URIs**:
   - Click **+ Add URI**.
   - Enter: `http://localhost:8000/auth/callback`
   - *Note: This must match the `REDIRECT_URI` in `backend/auth.py` exactly.*
6. Click **Create**.

## 5. Copy Keys
1. A popup will show your Client ID and Client Secret.
2. Copy **Client ID** to `GOOGLE_CLIENT_ID` in your `.env` file.
3. Copy **Client Secret** to `GOOGLE_CLIENT_SECRET` in your `.env` file.
