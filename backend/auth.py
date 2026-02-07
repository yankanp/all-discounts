from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
import os
import urllib.parse
import json
import uuid
import httpx
import logging
import base64
from typing import Optional
from services.gmail import GmailService

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/callback" 

# In-Memory Cache for Tokens
TOKEN_CACHE = {}

@router.get("/login")
def login_url(scan_history: Optional[str] = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
         return JSONResponse(content={"error": "Missing Server Credentials in .env"}, status_code=500)

    # Encode state
    state_data = {}
    if scan_history:
        try:
            # It's a JSON string of { email: timestamp_str }
            state_data['scan_history'] = json.loads(scan_history)
        except:
            pass
    
    state_json = json.dumps(state_data)
    state = base64.urlsafe_b64encode(state_json.encode()).decode()

    scope = "https://www.googleapis.com/auth/gmail.readonly"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"url": url, "mode": "live"}

@router.get("/callback")
async def callback(code: str, state: Optional[str] = None):
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=payload)
        token_data = resp.json()
    
    if "error" in token_data:
        return JSONResponse(content=token_data, status_code=400)

    token_data["client_id"] = GOOGLE_CLIENT_ID
    token_data["client_secret"] = GOOGLE_CLIENT_SECRET


    start_timestamp = None
    if state:
        try:
            state_json = base64.urlsafe_b64decode(state.encode()).decode()
            data = json.loads(state_json)
            
            # Support both legacy last_scan and new scan_history
            if 'scan_history' in data:
                 history = data['scan_history']
                 
                 # We need the user's email to pick the right timestamp
                 # We have the access_token in token_data, so we can fetch profile now
                 from services.gmail import GmailService
                 temp_service = GmailService(token_data)
                 user_profile = temp_service.get_user_profile()
                 email_address = user_profile.get('emailAddress')
                 
                 if email_address and email_address in history:
                     ts = history[email_address]
                     start_timestamp = float(ts) / 1000.0
            
            elif 'last_scan' in data:
                 start_timestamp = float(data['last_scan']) / 1000.0

        except Exception as e:
            logging.error(f"State decode error: {e}")

    token_data["start_timestamp"] = start_timestamp

    # Generate a temporary Token ID
    token_id = str(uuid.uuid4())
    TOKEN_CACHE[token_id] = token_data
    
    # Always redirect to Scanning (which is now WebLLM only)
    return RedirectResponse(url=f"http://localhost:3000/scanning?token={token_id}")

@router.get("/raw_messages/{token_id}")
def get_raw_messages(token_id: str):
    """
    Fetches raw emails for Client-Side AI processing.
    """
    token_data = TOKEN_CACHE.get(token_id)
    if not token_data:
        return JSONResponse(content={"error": "Invalid Token ID"}, status_code=404)

    start_timestamp = token_data.get("start_timestamp")
    gmail_service = GmailService(token_data)
    
    # Get User Email
    user_profile = gmail_service.get_user_profile()
    email_address = user_profile.get('emailAddress', 'unknown')

    # Fetch latest emails
    emails = gmail_service.fetch_promotional_emails(
        max_results=60, 
        start_timestamp=start_timestamp
    )
    
    if token_id in TOKEN_CACHE:
         del TOKEN_CACHE[token_id]
         
    return {
        "email": email_address,
        "messages": emails
    }
