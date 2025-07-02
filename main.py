import os
import json
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import openai
import requests

load_dotenv()

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
notion_token = os.getenv("NOTION_TOKEN")
menu_db = os.getenv("MENU_DATABASE_ID")
order_db = os.getenv("ORDER_DATABASE_ID")

headers = {
    "Authorization": f"Bearer {notion_token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# 🔰 取得 Notion 菜單
def get_menu_items():
    url = f"https://api.notion.com/v1/databases/{menu_db}/query"
    res = requests.post(url, headers=headers)
    data = res.json()

    print("Notion 回傳資料：", data)
    print("Notion 回傳 JSON:", data)

    items = []
    if "results" not in data:
        return [{"name": "❌ 無法從 Notion 取得菜單資料", "price": 0}]

    for result in data["results"]:
        try:
            name = result["properties"]["餐點名稱"]["title"][0]["text"]["content"]
            price = result["properties"]["價格"]["number"]
            items.append({"name": name, "price": price})
        except Exception as e:
            print("菜單資料解析錯誤：", e)

    return items

# 🔰 加入訂單到 Notion
def add_order_to_notion(items, total):
    order_title = ", ".join([f'{i["name"]} x{i["qty"]}' for i in items])
    new_page = {
        "parent": {"database_id": order_db},
        "properties": {
            "訂單內容": {
                "title": [{"text": {"content": order_title}}]
            },
            "總價": {
                "number": total
            }
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=new_page)
    return res.status_code == 200

@app.route('/')
def index():
    return 'Tanawat Order API is working! 🚀'

@app.route('/order', methods=['POST'])
def order():
    try:
        user_input = request.json.get("text", "")
        print("收到請求：", user_input)
        menu = get_menu_items()
        print("取得菜單：", menu)

        prompt = f"""你是一位點餐機器人，請根據使用者輸入分析點餐項目：
使用者輸入：「{user_input}」
目前菜單如下：
{[f'{item["name"]}（{item["price"]}元）' for item in menu]}
請輸出 JSON 格式：例如：
[{{"name": "Pad Thai", "qty": 1}}, {{"name": "奶茶", "qty": 2}}]"""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        gpt_reply = response["choices"][0]["message"]["content"]
        print("GPT 回傳：", gpt_reply)

        parsed = json.loads(gpt_reply)

        total = 0
        result = []
        for item in parsed:
            match = next((m for m in menu if m["name"] == item["name"]), None)
            if match:
                qty = item.get("qty", 1)
                subtotal = match["price"] * qty
                total += subtotal
                result.append({"name": match["name"], "qty": qty, "price": match["price"]})

        add_order_to_notion(result, total)

        return jsonify({
            "order": result,
            "total": total,
            "message": f"點餐成功！總金額為 NT${total} 元"
        })

    except json.JSONDecodeError as e:
        print("❌ JSON 解碼失敗：", e)
        print("錯誤內容：", gpt_reply)
        return jsonify({"error": "解析失敗"}), 400
    except Exception as e:
        print("❌ 伺服器錯誤：", e)
        traceback.print_exc()
        return jsonify({"error": "伺服器錯誤"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
