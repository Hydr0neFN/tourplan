[English](README.md) · **繁體中文**

# 揪日子 tourplan

**專為團體出遊打造的輕量自架選日子應用程式 — 適合所有家庭成員，包含對科技最不熟悉的長輩。**
<img width="503" height="861" alt="image" src="https://github.com/user-attachments/assets/d457e1fe-2d1f-4dbe-b010-eb2190a90c7d" />

<img width="867" height="866" alt="image" src="https://github.com/user-attachments/assets/b54eff93-ca3a-41a1-b8a5-8751dbc59c90" />

一個超輕量的「揪團選日子」網頁app：主辦人開一個規劃、圈出可選的日期範圍，家人朋友點開連結、點日期表達「可以／不行」，主辦人一眼看出哪天最多人有空。專為手機與長輩設計。

類似 Doodle/When2meet，但：預設邏輯相反（每天預設為「*可以*」，點擊表示「*不行*」）、僅二元投票、以 emoji 頭像取代帳號，簡單到連長輩都能輕鬆上手。

## 功能特點

- **點擊切換** — 每個可規劃的日期初始均為綠色（可以）。點擊一次 → 紅色（不行）。再點一次 → 切換回來。無需填寫表單、無需拖曳選取，絕不讓人摸不著頭緒。
- **訪客無需帳號** — 訪客可自由填寫姓名（或略過）。身份以簽章 cookie 識別；再次造訪的訪客會保留其投票。未填姓名的訪客會從 24 種圖示庫中獲得一個 emoji 暱稱（小花 🌸、小蛙 🐸、…）。
- **一目了然的統計** — 每個日期方格以微型 emoji 列顯示誰*可以*出席（`🐸+2` 溢出顯示）；不能出席的人特意不顯示在方格內（混雜的排列會使受測長輩感到困惑），改顯示在參與者名單中。
- **個人彙整摘要** — 參與者名單將每個人的「不行」日期顯示為壓縮後的範圍（`8/11、14–15`）；點擊可展開完整明細。設計上使誤觸絕不會改變狀態 — 對長輩友善安全。
- **跨月份日曆** — 日期範圍可跨越多個月份；垂直堆疊排列（桌機版為雙欄並排）。
- **多項規劃同時進行** — 每個規劃都會獲得一個無法猜測的專屬連結（`/t/<slug>`）；主辦人可依需求建立任意數量的規劃。
- **截止收單 (Voting deadline)** — 每個規劃可選填截止日期（台灣時間，含當日）；到期自動鎖定投票，亦提供手動關閉／重新開放開關。
- **匿名切換** — 每個規劃可設定：顯示真實姓名，或將所有人顯示為 emoji 暱稱（主辦人查看結果時一律顯示真實姓名）。
- **多主辦人** — 單一實例支援多個管理員帳號；每位主辦人僅能查看與管理自己的規劃。主辦人可直接從結果列表中移除參與者（及其投票）— 對於無痕視窗或清除 cookie 產生的幽靈身份非常實用。
- **首次造訪教學** — 3 步驟覆蓋導覽，可透過 `?` 按鈕重新播放。
- **雙語支援** — 繁體中文（台灣）預設，英文切換開關，透過 per-user cookie 儲存偏好。
- **近即時同步** — 5 秒輪詢 + 分頁重新獲得焦點時立即重新整理；所有回應皆帶有 `Cache-Control: no-store`，使行動瀏覽器絕不顯示過期投票。

## 技術堆疊

FastAPI · SQLite (WAL) · Jinja2 · 原生 JS。無需建置步驟、無需 Node、無需帳號資料庫 — 一次 `pip install`，約 50 MB 記憶體。在 Raspberry Pi 上運作順暢。

密碼採用 scrypt 雜湊（stdlib），工作階段與訪客 token 均為 HMAC 簽章 cookie，管理員表單具備 CSRF 保護，登入／加入端點設有速率限制。應用程式僅綁定 loopback — 請在前端搭配反向代理或 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)。

## 快速開始

```bash
git clone https://github.com/<you>/tourplan && cd tourplan
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m uvicorn app.main:app --port 8100
```

開啟 `http://127.0.0.1:8100/admin` — 首次登入為 `admin` / `admin`；您必須立即設定新密碼。建立規劃、複製連結並分享出去。

## 部署（Raspberry Pi / 任何 Debian 系列主機 + Cloudflare Tunnel）

```bash
# on the box
sudo apt install -y python3-venv sqlite3
git clone https://github.com/<you>/tourplan /root/tourplan
cd /root/tourplan
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# systemd
sudo cp deploy/tourplan.service /etc/systemd/system/
sudo nano /etc/systemd/system/tourplan.service   # set TOURPLAN_BASE_URL + paths for your box
sudo systemctl daemon-reload && sudo systemctl enable --now tourplan
```

Cloudflare Tunnel ingress（位於 `/etc/cloudflared/config.yml` 的 catch-all 之上）：

```yaml
- hostname: plan.example.com
  service: http://localhost:8100
```

建議的強化措施：在 Tunnel 上線**之前**更改預設管理員密碼，並新增 Cloudflare WAF 規則將 `/admin*` 限制在您所在的國家／地區。

每日夜間備份（SQLite 線上備份，7 份輪替複本）：

```cron
15 4 * * * sqlite3 /root/tourplan/data/tourplan.db ".backup /root/backups/tourplan-$(date +\%a).db"
```

## 環境設定

| 環境變數 | 預設值 | 意義 |
|---|---|---|
| `TOURPLAN_BASE_URL` | request-derived | 管理員「複製連結」按鈕所使用的公開基礎 URL |
| `TOURPLAN_MAX_VISITORS` | `60` | 每個規劃的最大參與者人數 |

所有狀態均儲存在 `data/`：`tourplan.db`（SQLite）與 `secret.key`（cookie 簽章金鑰 — 遺失會使所有人登出；外洩會讓任何人都能偽造 session）。

## 設計理念

- **僅儲存「不行」日期** — 加入規劃即代表「所有日期都可以」；僅儲存拒絕的日期。最常見的情況（多數人多數日子有空）為 0 列資料。
- **無高亮模式** — 點擊參與者絕不改變日曆樣式（早期設計曾有此功能；誤觸時會讓受測長輩感到困惑）。有空／沒空的詳細資訊改以純文字範圍呈現。
- **時區** — 無論伺服器時區為何，截止時間一律以 UTC+8（台灣）計算。

## 授權條款

MIT — 詳見 [LICENSE](LICENSE)。
