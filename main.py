```python
import os
import json
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
from openai import OpenAI, OpenAIError

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in environment")
client = OpenAI(api_key=OPENAI_API_KEY)

# Notion configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
MENU_DB_ID = os.getenv("MENU_DATABASE_ID")
ORDER_DB_ID = os.getenv("ORDER_DATABASE_ID")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Health check endpoint
@app.route('/', methods=["GET"])
def health_check():
    return 'OK', 200

# Fetch menu items from Notion database
def get_menu():
    url = f"https://api.notion.com/v1/databases/{MENU_DB_ID}/query"
    resp = requests.post(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json().get("results", [])
    menu = []
    for page in data:
        try:
            name = page["properties"]["餐點名稱"]["title"][0]["text"]["content"]
            price = page["properties"]["價格"]["number"]
            menu.append({"name": name, "price": price})
        except Exception:
            continue
    return menu

# Save order to Notion database
def save_order(items, total):
    title = ", ".join([f"{i['name']} x{i['qty']}" for i in items])
    page = {
        "parent": {"database_id": ORDER_DB_ID},
        "properties": {
            "訂單內容": {"title": [{"text": {"content": title}}]},
            "總價": {"number": total}
        }
    }
    resp = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page)
    resp.raise_for_status()

# Order endpoint
@app.route('/order', methods=['POST'])
def create_order():
    try:
        data = request.get_json(force=True)
        text = data.get('text')
        if not text:
            return jsonify({"error": "請提供 'text' 欄位"}), 400

        # Load menu
        menu = get_menu()

        # Build prompt for GPT
        prompt = (
            "你是一位餐廳點餐助手，只回傳 JSON array，格式: ``[{"name":"Pad Thai","qty":1}]``\n"
            f"使用者點餐: {text}\n"
            f"菜單有: {menu}"
        )

        # Call OpenAI
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = resp.choices[0].message.content

        # Extract JSON array
        start = reply.find('[')
        end = reply.rfind(']')
        if start < 0 or end < 0:
            raise ValueError("未在回覆中找到 JSON 陣列")
        orders = json.loads(reply[start:end+1])

        # Calculate total
        result = []
        total = 0
        for o in orders:
            name = o.get('name')
            qty = int(o.get('qty', 1))
            match = next((m for m in menu if m['name'] == name), None)
            if match:
                result.append({"name": name, "qty": qty, "price": match['price']})
                total += match['price'] * qty

        # Save to Notion
        save_order(result, total)

        return jsonify({"order": result, "total": total}), 200

    except (ValueError, json.JSONDecodeError):
        return jsonify({"error": "解析失敗，請確認輸入格式"}), 400
    except requests.HTTPError as e:
        return jsonify({"error": "Notion API 錯誤: " + str(e)}), 500
    except OpenAIError as e:
        return jsonify({"error": "OpenAI API 錯誤: " + str(e)}), 500
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "伺服器內部錯誤"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
```
