import os
import json
import base64
import asyncio
import datetime
from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openai import OpenAI
import websockets

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize OpenAI & ElevenLabs
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "21m00Tcm4TlvDq8ikWAM" # Change to your preferred voice ID

# 1. Google Calendar Logic
def get_calendar_service():
    creds_json = os.getenv("GOOGLE_TOKEN_JSON")
    creds = Credentials.from_authorized_user_info(json.loads(creds_json))
    return build('calendar', 'v3', credentials=creds)

def create_calendar_event(name, date, time):
    service = get_calendar_service()
    start_time = datetime.datetime.fromisoformat(f"{date}T{time}:00")
    event = {
        'summary': f"Meeting with {name}",
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': (start_time + datetime.timedelta(minutes=30)).isoformat(), 'timeZone': 'UTC'},
    }
    service.events().insert(calendarId='primary', body=event).execute()
    return {"status": "success", "message": "Event created on Google Calendar"}

# 2. Tool Definitions
TOOLS = [{
    "type": "function",
    "function": {
        "name": "create_calendar_event",
        "description": "Schedules a meeting in Google Calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"}
            },
            "required": ["name", "date", "time"]
        }
    }
}]

# 3. WebSocket for Voice
@app.websocket("/voice")
async def voice_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Connect to ElevenLabs WebSocket
    el_uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id=eleven_turbo_v2_5"

    async with websockets.connect(el_uri) as el_ws:
        await el_ws.send(json.dumps({
            "text": " ",
            "xi_api_key": ELEVENLABS_API_KEY,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }))

        async def listen_and_stream():
            while True:
                # Receive transcript from frontend or STT
                user_msg = await websocket.receive_text()

                # Get AI Response + Handle Tool Calls
                messages = [
                    {"role": "system", "content": "You are a concise scheduling assistant. Use the calendar tool when ready."},
                    {"role": "user", "content": user_msg}
                ]

                response = client.chat.completions.create(model="gpt-4o", messages=messages, tools=TOOLS)
                ai_msg = response.choices[0].message

                if ai_msg.tool_calls:
                    for call in ai_msg.tool_calls:
                        args = json.loads(call.function.arguments)
                        create_calendar_event(**args)
                    final_text = "I've scheduled that for you!"
                else:
                    final_text = ai_msg.content

                # Send text to ElevenLabs for streaming audio
                await el_ws.send(json.dumps({"text": final_text, "flush": True}))

        async def el_to_frontend():
            while True:
                msg = await el_ws.recv()
                data = json.loads(msg)
                if data.get("audio"):
                    await websocket.send_text(data["audio"])

        await asyncio.gather(listen_and_stream(), el_to_frontend())