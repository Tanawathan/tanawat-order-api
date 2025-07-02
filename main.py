import os
import json
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
import openai

# Load environment variables
load_dotenv()

# Validate required environment variables
required_vars = ['OPENAI_API_KEY', 'NOTION_TOKEN', 'MENU_DATABASE_ID', 'ORDER_DATABASE_ID']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    print(f"Error: Missing environment variables: {', '.join(missing)}")
    print("Please set these in your environment before starting the app.")
    exit(1)

# Initialize Flask app
app = Flask(__name__)

# Configure OpenAI and Notion
openai.api_key = os.getenv("OPENAI_API_KEY")
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

# Fetch menu items from Notion
def get_menu():
    url = f"https://api.notion.com/v1/databases/{MENU_DB_ID}/query"
    resp = requests.post(url, headers=HEADERS)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # Log detailed error for debugging
        print(f"Error fetching menu from Notion: {e}\nResponse content: {resp.text}")
        # Raise a user-friendly exception
        raise Exception("無法從 Notion 取得菜單，請確認 MENU_DATABASE_ID 與 NOTION_TOKEN 是否正確。")

    pages = resp.json().get('results', [])
    menu = []
    for p in pages:
        try:
            name = p['properties']['餐點名稱']['title'][0]['text']['content']
            price = p['properties']['價格']['number']
            menu.append({'name': name, 'price': price})
        except Exception:
            # Skip pages with unexpected structure
            continue
    return menu

# Save order to Notion
def save_order(items, total):
    title = ", ".join([f"{i['name']} x{i['qty']}" for i in items])
    body = {
        'parent': {'database_id': ORDER_DB_ID},
        'properties': {
            '訂單內容': {'title': [{'text': {'content': title}}]},
            '總價': {'number': total}
        }
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=body)
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Error saving order to Notion: {e}\nResponse content: {r.text}")
        raise Exception("無法將訂單儲存到 Notion，請稍後再試。")

# Order endpoint
@app.route('/order', methods=['POST'])
def create_order():
    try:
        data = request.get_json(force=True)
        text = data.get('text')
        if not text:
            return jsonify({'error': "請提供 'text' 欄位"}), 400

        # Retrieve menu from Notion
        menu = get_menu()
        if not menu:
            return jsonify({'error': '菜單目前為空，請稍後再試或聯絡管理員。'}), 500

        # Build prompt for GPT
        prompt = (
            "你是一位餐廳點餐助手，只回傳 JSON array，格式: [{\"name\":\"Pad Thai\",\"qty\":1}]\n"
            f"使用者點餐: {text}\n"
            f"菜單: {menu}"
        )

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0
        )
        content = response.choices[0].message.content

        # Extract JSON array from AI response
        start = content.find('[')
        end = content.rfind(']') + 1
        if start < 0 or end < 1:
            return jsonify({'error': '未解析到訂單列表'}), 400
        orders = json.loads(content[start:end])

        # Calculate totals
        result = []
        total = 0
        for o in orders:
            name = o.get('name')
            qty = int(o.get('qty', 1))
            match = next((m for m in menu if m['name'] == name), None)
            if match:
                result.append({'name': name, 'qty': qty, 'price': match['price']})
                total += match['price'] * qty

        # Save order to Notion
        save_order(result, total)
        return jsonify({'order': result, 'total': total}), 200

    except Exception as e:
        # Log stack trace for debugging
        traceback.print_exc()
        return jsonify({'error': '伺服器內部錯誤', 'detail': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
