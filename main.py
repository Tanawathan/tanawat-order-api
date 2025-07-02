from flask import Flask, request, jsonify
import os
import openai
import requests

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
MENU_DATABASE_ID = os.getenv("MENU_DATABASE_ID")
ORDER_DATABASE_ID = os.getenv("ORDER_DATABASE_ID")

@app.route("/")
def home():
    return "Welcome to the Tanawat Order Bot API!"

@app.route("/order", methods=["POST"])
def order():
    data = request.get_json()
    user_order = data.get("order")

    if not user_order:
        return jsonify({"error": "Missing 'order' field in request body."}), 400

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    notion_data = {
        "parent": { "database_id": ORDER_DATABASE_ID },
        "properties": {
            "Order": {
                "title": [{ "text": { "content": user_order } }]
            }
        }
    }

    response = requests.post("https://api.notion.com/v1/pages", headers=headers, json=notion_data)

    if response.status_code == 200:
        return jsonify({"message": "Order added to Notion successfully."})
    else:
        return jsonify({"error": "Failed to add order to Notion", "details": response.text}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
