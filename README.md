# Tanawat Order API

一個基於 Flask + Notion + OpenAI 的點餐後端服務。

## 功能

- `GET /`：健康檢查 → 回傳 `OK`
- `GET /menu`：從 Notion 拿菜單資料
- `POST /parse`：解析使用者自由文字成訂單項目（不存儲）
- `POST /order`：接收前端傳來的 items，計算總價並寫入 Notion Orders 資料庫

## 快速上手

1. **複製環境設定**  
   ```bash
   cp .env.example .env
   ```
   並填入你的金鑰、Notion 資料庫 ID。

2. **安裝依賴**  
   ```bash
   pip install -r requirements.txt
   ```

3. **啟動服務**  
   ```bash
   flask run
   ```
   or
   ```bash
   python main.py
   ```
   預設監聽 `0.0.0.0:5000`。

4. **部署**  
   - 在 Render、Heroku、Vercel 等平台，將上述環境變數逐一設置到平台設定中（千萬別上傳 `.env`）。

## 環境變數

| 變數               | 說明                           |
|--------------------|--------------------------------|
| `OPENAI_API_KEY`   | OpenAI API Key                 |
| `NOTION_TOKEN`     | Notion Integration Token       |
| `MENU_DATABASE_ID` | Notion “菜單” 資料庫 ID         |
| `ORDER_DATABASE_ID`| Notion “訂單” 資料庫 ID         |
| `PORT`             | Flask 監聽埠號（選填，預設 5000）|

## 專案結構

```
.
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
