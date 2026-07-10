"""
Quick test script — sends a message with your 5 sample custom emoji
to a Telegram channel, via the local microservice.

Before running:
1. Make sure `uvicorn main:app --reload --port 8000` is running in another terminal.
2. Edit CHAT_ID below to your real channel (@username, or -100... numeric id for private channels).
3. Edit BRIDGE_API_KEY below to match your .env value if you changed it.

Run:
    python test_send.py
"""

import requests

BRIDGE_URL = "http://localhost:8000/send-message"
BRIDGE_API_KEY = "xk9m2p7qL4vN8wR3tY6zA1bC5dE0fG2h"  # must match your .env

CHAT_ID = "@TestSamyTG_Bridge"  # <-- EDIT THIS to your real channel

payload = {
    "chat_id": CHAT_ID,
    "text": "\U0001F44D BIG NEWS EVERYONE \U0001F680 Sales are going \U0001F4C8 and the \U0001F4B0 \U0001F4B0 keeps coming in! We're \U0001F929 \U0001F48E \U0001F496 about it!",
    "entities": [
        {"type": "custom_emoji", "offset": 0,  "length": 2, "custom_emoji_id": "5312026254751313956"},  # thumbs-up
        {"type": "custom_emoji", "offset": 21, "length": 2, "custom_emoji_id": "5188481279963715781"},  # rocket
        {"type": "custom_emoji", "offset": 40, "length": 2, "custom_emoji_id": "5382164415019768638"},  # sales-up
        {"type": "custom_emoji", "offset": 51, "length": 2, "custom_emoji_id": "5201873447554145566"},  # money
        {"type": "custom_emoji", "offset": 54, "length": 2, "custom_emoji_id": "5417924076503062111"},  # money
        {"type": "custom_emoji", "offset": 80, "length": 2, "custom_emoji_id": "5240075712773235252"},  # star-eyes
        {"type": "custom_emoji", "offset": 83, "length": 2, "custom_emoji_id": "5462902520215002477"},  # diamond
        {"type": "custom_emoji", "offset": 86, "length": 2, "custom_emoji_id": "5303310030940952439"},  # heart
    ],
}

response = requests.post(
    BRIDGE_URL,
    headers={"X-API-Key": BRIDGE_API_KEY, "Content-Type": "application/json"},
    json=payload,
)

print("Status code:", response.status_code)
print("Response body:", response.text)
