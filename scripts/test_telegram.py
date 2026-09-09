import os
import requests

token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

message = "Test RadarJohBot, la connexion fonctionne."

url = f"https://api.telegram.org/bot{token}/sendMessage"
response = requests.post(url, data={"chat_id": chat_id, "text": message})

print(response.status_code, response.text)
