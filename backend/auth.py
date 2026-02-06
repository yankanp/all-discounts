from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
import os
import urllib.parse
import json
import uuid
import httpx
import logging
import base64
from typing import Optional
from services.gmail import GmailService
from agents.extractor import ExtractorAgent

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/callback" 

# In-Memory Cache for Tokens (Exchange code for token -> Store here -> Stream uses it)
# token_id -> token_data (dict)
# Structure: { ...token, 'start_timestamp': float }
TOKEN_CACHE = {}

@router.get("/login")
def login_url(last_scan: Optional[str] = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
         return JSONResponse(content={"error": "Missing Server Credentials in .env"}, status_code=500)

    # Encode state
    state_data = {}
    if last_scan:
        state_data['last_scan'] = last_scan
    
    # Simple base64 encoding for state to survive the redirect chain
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

    # Decode state to get last_scan
    start_timestamp = None
    if state:
        try:
            state_json = base64.urlsafe_b64decode(state.encode()).decode()
            data = json.loads(state_json)
            start_timestamp = data.get('last_scan')
            if start_timestamp:
                start_timestamp = float(start_timestamp) / 1000.0 # Convert js ms to python seconds
        except Exception as e:
            logging.error(f"State decode error: {e}")

    token_data["start_timestamp"] = start_timestamp

    # Generate a temporary Token ID
    token_id = str(uuid.uuid4())
    TOKEN_CACHE[token_id] = token_data
    
    # Redirect to Frontend Scanning Page
    return RedirectResponse(url=f"http://localhost:3000/scanning?token={token_id}")

@router.get("/stream/{token_id}")
def stream_scan(token_id: str):
    token_data = TOKEN_CACHE.get(token_id)
    if not token_data:
        return JSONResponse(content={"error": "Invalid Token ID"}, status_code=404)

    start_timestamp = token_data.get("start_timestamp")

    # We use a generator logic here
    def event_generator():
        try:
            yield f"event: log\ndata: {json.dumps({'msg': 'Initializing Gmail Service...'})}\n\n"
            
            gmail_service = GmailService(token_data)
            
            if start_timestamp:
                import datetime
                date_str = datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
                yield f"event: log\ndata: {json.dumps({'msg': f'Searching new emails since {date_str}...'})}\n\n"
            else:
                yield f"event: log\ndata: {json.dumps({'msg': 'Full Scan: Last 6 months...'})}\n\n"
            
            # Fetch 60 emails as requested for production
            emails = gmail_service.fetch_promotional_emails(
                max_results=60, 
                start_timestamp=start_timestamp
            )
            
            count = len(emails)
            yield f"event: log\ndata: {json.dumps({'msg': f'Found {count} new emails. Starting AI extraction...'})}\n\n"
            
            extractor = ExtractorAgent()
            final_coupons = []
            
            # Run generator
            for event in extractor.process_emails_gen(emails):
                if event['type'] == 'coupon':
                    final_coupons.append(event['data'].dict())
                    # Log the success
                    yield f"event: log\ndata: {json.dumps({'msg': 'Saved Coupon', 'type': 'success'})}\n\n"
                
                elif event['type'] == 'log':
                    yield f"event: log\ndata: {json.dumps(event)}\n\n"
                
                elif event['type'] == 'progress':
                    yield f"event: progress\ndata: {json.dumps(event)}\n\n"
            
            # DONE
            completion_payload = {
                "msg": "Scan Complete", 
                "count": len(final_coupons),
                "coupons": final_coupons
            }
            yield f"event: complete\ndata: {json.dumps(completion_payload, default=str)}\n\n"
            
            # Cleanup
            if token_id in TOKEN_CACHE:
                del TOKEN_CACHE[token_id]

        except Exception as e:
            logging.error(f"Stream Error: {e}")
            yield f"event: log\ndata: {json.dumps({'msg': f'Error: {str(e)}', 'type': 'error'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
