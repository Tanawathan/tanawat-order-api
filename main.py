import os
import json
import re
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
from openai import OpenAI, OpenAIError

# 載入環境變數
load_dotenv()

app = Flask(__name__)

# 初始化 OpenAI 客戶端
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Notion Config
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
MENU_DB = os.getenv("MENU_DATABASE_ID")
ORDER_DB = os.getenv("ORDER_DATABASE_ID")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# 取得菜單
def get_menu():
    url = f"https://api.notion.com/v1/databases/{MENU_DB}/query"
    try:
        res = requests.post(url, headers=HEADERS)
        res.raise_for_status()
    except requests.exceptions.HTTPError:
        # 資料庫 ID 錯誤或 Notion API 拒絕
        raise
    data = res.json().get("results", [])
    items = []
    for entry in data:
        try:
            name = entry["properties"]["餐點名稱"]["title"][0]["text"]["content"]
            price = entry["properties"]["價格"]["number"]
            items.append({"name": name, "price": price})
        except Exception:
            continue
    return items

# 訂單寫入 Notion
def save_order(order_items, total):
    title = ", ".join([f"{i['name']} x{i['qty']}" for i in order_items])
    page = {
        "parent": {"database_id": ORDER_DB},
        "properties": {
            "訂單內容": {"title": [{"text": {"content": title}}]},
            "總價": {"number": total}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page)
    res.raise_for_status()

@app.route('/', methods=["GET"])
def health():
    return 'OK', 200

@app.route('/order', methods=['POST'])
def order():
    try:
        body = request.get_json(force=True)
        user_text = body.get('text', '')
        if not user_text:
            return jsonify({"error": "請提供 text 欄位"}), 400

        try:
            menu = get_menu()
        except requests.exceptions.HTTPError:
            return jsonify({"error": "無法取得菜單，請檢查 MENU_DATABASE_ID"}), 400

        prompt = (
            "你是一位點餐機器人，僅輸出純粹 JSON 陣列，格式: "
            "[{\"name\": \"Pad Thai\", \"qty\": 1}]" +
            f"。使用者輸入: {user_text}。菜單: {menu}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = resp.choices[0].message.content

        # 擷取陣列
        match = re.search(r"\[.*\]", reply, re.S)
        if not match:
            raise ValueError("未找到 JSON 陣列")
        orders = json.loads(match.group(0))

        total = 0
        valid = []
        for o in orders:
            m = next((x for x in menu if x['name'] == o.get('name')), None)
            if m:
                qty = o.get('qty', 1)
                total += m['price'] * qty
                valid.append({"name": m['name'], "qty": qty, "price": m['price']})

        save_order(valid, total)
        return jsonify({"order": valid, "total": total}), 200

    except (ValueError, json.JSONDecodeError):
        return jsonify({"error": "解析失敗"}), 400
    except OpenAIError:
        return jsonify({"error": "OpenAI API 錯誤, 請檢查帳號狀態"}), 500
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "伺服器錯誤"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
