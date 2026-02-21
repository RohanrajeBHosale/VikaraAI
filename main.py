import os
import json
import datetime
from fastapi import FastAPI, Request, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

app = FastAPI()

# Vercel provides HTTPS automatically, so we only use this for local testing
if os.getenv("VERCEL_ENV") != "production":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_calendar_service():
    # Load credentials from Vercel Environment Variables
    creds_json = os.getenv("GOOGLE_TOKEN_JSON")
    if not creds_json:
        return None

    info = json.loads(creds_json)
    creds = Credentials.from_authorized_user_info(info)

    if not creds.valid and creds.refresh_token:
        creds.refresh(GoogleRequest())
    return build('calendar', 'v3', credentials=creds)

@app.post("/api/schedule")
async def handle_elevenlabs_tool(request: Request):
    body = await request.json()

    # ElevenLabs sends tool arguments in the "parameters" field
    args = body.get("parameters", {})
    name = args.get("name")
    date_str = args.get("date")  # YYYY-MM-DD
    time_str = args.get("time")  # HH:MM

    service = get_calendar_service()
    if not service:
        raise HTTPException(status_code=401, detail="Authentication missing.")

    start_time = datetime.datetime.fromisoformat(f"{date_str}T{time_str}:00")
    end_time = start_time + datetime.timedelta(minutes=30)

    event = {
        'summary': name,
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
    }

    result = service.events().insert(calendarId='primary', body=event).execute()
    return {"status": "success", "event_link": result.get('htmlLink')}