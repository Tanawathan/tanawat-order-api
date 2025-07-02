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

# Debug: print loaded values (token masked)
OPENAI_KEY_OK = 'set' if os.getenv('OPENAI_API_KEY') else 'unset'
NOTION_KEY_OK = 'set' if os.getenv('NOTION_TOKEN') else 'unset'
MENU_DB_ID = os.getenv('MENU_DATABASE_ID')
ORDER_DB_ID = os.getenv('ORDER_DATABASE_ID')
print(f"Environment loaded -> OPENAI_API_KEY={OPENAI_KEY_OK}, NOTION_TOKEN={NOTION_KEY_OK}, MENU_DB_ID={MENU_DB_ID}, ORDER_DB_ID={ORDER_DB_ID}")

# Configure APIs
openai.api_key = os.getenv('OPENAI_API_KEY')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
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
    Fetch the menu items from Notion.
    Returns a list of dicts: [{ 'name': str, 'price': float }]
    """
    url = f"https://api.notion.com/v1/databases/{MENU_DB_ID}/query"
    print(f"Fetching menu from Notion at {url}")
    resp = requests.post(url, headers=NOTION_HEADERS)
    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch menu: {e}\nResponse text: {resp.text}")
        raise RuntimeError("Cannot fetch menu. Check Notion credentials and database ID.")
    data = resp.json().get('results', [])
    menu = []
    for page in data:
        props = page.get('properties', {})
        title = props.get('餐點名稱', {}).get('title', [])
        price = props.get('價格', {}).get('number')
        if title and price is not None:
            name = title[0].get('text', {}).get('content')
            menu.append({'name': name, 'price': price})
    print(f"Menu items fetched: {menu}")
    return menu


def save_order(order_items, total):
    """
    Save the order back to Notion.
    """
    title = ", ".join(f"{item['name']} x{item['qty']}" for item in order_items)
    payload = {
        'parent': { 'database_id': ORDER_DB_ID },
        'properties': {
            '訂單內容': { 'title': [{ 'text': { 'content': title } }] },
            '總價': { 'number': total }
        }
    }
    url = 'https://api.notion.com/v1/pages'
    print(f"Saving order to Notion: {payload}")
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to save order: {e}\nResponse text: {resp.text}")
        raise RuntimeError("Cannot save order. Check Notion credentials and database ID.")

# --- Routes ---
@app.route('/', methods=['GET'])
def health_check():
    return 'OK', 200

@app.route('/order', methods=['POST'])
def create_order():
    try:
        body = request.get_json(force=True)
        text = body.get('text')
        if not text:
            return jsonify({ 'error': "Missing 'text' in request body." }), 400

        # Step 1: Get menu
        menu = get_menu()
        if not menu:
            return jsonify({ 'error': 'No menu items available.' }), 500

        # Step 2: Ask OpenAI to parse order
        prompt = (
            "你是一位點餐助手，只回傳 JSON array，格式: [{\"name\":\"Pad Thai\",\"qty\":1}]\n"
            f"使用者輸入: {text}\n"
            f"菜單: {menu}"
        )
        print(f"Sending prompt to OpenAI: {prompt}")
        ai_resp = openai.ChatCompletion.create(
            model='gpt-4',
            messages=[{ 'role': 'user', 'content': prompt }],
            temperature=0
        )
        content = ai_resp.choices[0].message.content
        print(f"OpenAI response: {content}")
        # Extract JSON
        start, end = content.find('['), content.rfind(']') + 1
        orders = json.loads(content[start:end])

        # Step 3: Calculate totals
        order_items = []
        total = 0
        for o in orders:
            name = o.get('name')
            qty = int(o.get('qty', 1))
            match = next((m for m in menu if m['name'] == name), None)
            if match:
                order_items.append({ 'name': name, 'qty': qty, 'price': match['price'] })
                total += match['price'] * qty

        # Step 4: Save to Notion
        save_order(order_items, total)
        return jsonify({ 'order': order_items, 'total': total }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({ 'error': 'Internal server error', 'detail': str(e) }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
