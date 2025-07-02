import os
import json
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
import openai

# --- Load and validate environment variables ---
load_dotenv()
REQUIRED_ENV = [
    'OPENAI_API_KEY',
    'NOTION_TOKEN',
    'MENU_DATABASE_ID',
    'ORDER_DATABASE_ID',
]
missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
if missing:
    print(f"Error: missing environment variables: {', '.join(missing)}")
    exit(1)

# Configure APIs
openai.api_key = os.getenv('OPENAI_API_KEY')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
MENU_DB_ID = os.getenv('MENU_DATABASE_ID')
ORDER_DB_ID = os.getenv('ORDER_DATABASE_ID')
NOTION_HEADERS = {
    'Authorization': f"Bearer {NOTION_TOKEN}",
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

# Initialize Flask
app = Flask(__name__)

# --- Utility functions ---
def get_menu():
    """
    Fetch menu items from Notion and return a list of {name, price}.
    """
    url = f"https://api.notion.com/v1/databases/{MENU_DB_ID}/query"
    resp = requests.post(url, headers=NOTION_HEADERS)
    resp.raise_for_status()
    data = resp.json().get('results', [])
    menu = []
    for page in data:
        props = page.get('properties', {})
        title_block = props.get('餐點名稱', {}).get('title', [])
        price = props.get('價格', {}).get('number')
        if title_block and price is not None:
            name = title_block[0].get('text', {}).get('content')
            menu.append({'name': name, 'price': price})
    return menu

def parse_order_text(text, menu):
    """
    Use OpenAI to parse free-text order input into JSON list of items.
    """
    prompt = (
        "你是一位點餐助手，只回傳 JSON array，格式: [{\"name\":\"Pad Thai\",\"qty\":1}]。"
        f"\n菜單: {menu}\n使用者輸入: {text}"
    )
    ai_resp = openai.ChatCompletion.create(
        model='gpt-4',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0
    )
    content = ai_resp.choices[0].message.content
    start = content.find('[')
    end = content.rfind(']') + 1
    return json.loads(content[start:end])

def save_order_to_notion(order_items, total):
    """
    Write the final order into Notion orders database.
    """
    title = ", ".join(f"{item['name']} x{item['qty']}" for item in order_items)
    payload = {
        'parent': {'database_id': ORDER_DB_ID},
        'properties': {
            '訂單內容': {'title': [{'text': {'content': title}}]},
            '總價': {'number': total}
        }
    }
    url = 'https://api.notion.com/v1/pages'
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    resp.raise_for_status()

# --- Routes ---
@app.route('/', methods=['GET'])
def health_check():
    return 'OK', 200

@app.route('/menu', methods=['GET'])
def route_menu():
    """Return menu items as JSON."""
    try:
        menu = get_menu()
        return jsonify(menu), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/parse', methods=['POST'])
def route_parse():
    """Parse free-text input into order items without saving."""
    try:
        data = request.get_json(force=True)
        text = data.get('text')
        if not text:
            return jsonify({'error': 'Missing text field'}), 400
        menu = get_menu()
        orders = parse_order_text(text, menu)
        return jsonify(orders), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': 'Internal parse error', 'detail': str(e)}), 500

@app.route('/order', methods=['POST'])
def route_order():
    """Finalize and save the order into Notion."""
    try:
        data = request.get_json(force=True)
        items = data.get('items')
        if not isinstance(items, list) or not items:
            return jsonify({'error': 'Invalid or empty items list'}), 400
        menu = get_menu()
        order_items = []
        total = 0
        for o in items:
            name = o.get('name')
            qty = int(o.get('qty', 1))
            match = next((m for m in menu if m['name'] == name), None)
            if match:
                order_items.append({'name': name, 'qty': qty, 'price': match['price']})
                total += match['price'] * qty
        save_order_to_notion(order_items, total)
        return jsonify({'order': order_items, 'total': total}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': 'Internal order error', 'detail': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
