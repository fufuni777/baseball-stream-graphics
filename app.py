import eventlet
import json
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import socket
import csv
from collections import defaultdict
from pathlib import Path

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# ================= 路徑設定 =================

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR/ "team_players.csv"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

PITCHER_STATS_FILE = DATA_DIR / "pitcher_stats.json"
BATTER_STATS_FILE  = DATA_DIR / "batter_stats.json"


def load_json(path: Path, default):
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] load_json({path}) failed:", e)
    return default


def save_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] save_json({path}) failed:", e)


# 開機時先把檔案讀進來當快取
pitcher_stats = load_json(PITCHER_STATS_FILE, {})   # { '投手名': {'np': 32}, ... }
batter_stats  = load_json(BATTER_STATS_FILE, {})    # { '打者名': {'batter_pa_recent': [...]} }

def load_players_from_csv(path: Path):
    """
    讀取 CSV (team, number, name)
    回傳格式:
        {
            '隊伍名': [
                {"num": "1", "name": "王小明"},
                {"num": "18", "name": "李大華"},
                ...
            ]
        }
    """
    players_by_team = defaultdict(list)
    if not path.exists():
        print(f"[WARN] 找不到檔案: {path}")
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                team   = (row.get("team") or "").strip()
                name   = (row.get("name") or "").strip()
                number = (row.get("number") or "").strip()

                if team and name:
                    players_by_team[team].append({
                        "num": number,
                        "name": name,
                    })

        print(f"[INFO] 成功讀取球隊資料: {list(players_by_team.keys())}")
        return dict(players_by_team)
    except Exception as e:
        print(f"[ERROR] 讀取 CSV 失敗: {e}")
        return {}

PLAYERS_BY_TEAM = load_players_from_csv(CSV_PATH)

# 初始化比賽狀態
score_data = {
    # 電視轉播區
    "away_team": "客隊", "home_team": "主隊",
    "away_logo_url": "", "home_logo_url": "",
    "away_score": 0, "home_score": 0,
    "inning": "1上",
    "pitcher": "", "batter": "",
    "np": 0,
    "balls": 0, "strikes": 0, "outs": 0,
    "bases": [False, False, False],
    "batter_pa_recent": [],
    "core_version": 0,

    # 完整記分板區
    "box_away": { "name": "客隊", "scores": [0]*9, "H": 0, "E": 0, "lineup": ["(待定)"]*9 },
    "box_home": { "name": "主隊", "scores": [0]*9, "H": 0, "E": 0, "lineup": ["(待定)"]*9 }
}

def update_player_stats_from_score():
    global pitcher_stats, batter_stats
    pitcher = (score_data.get("pitcher") or "").strip()
    batter  = (score_data.get("batter") or "").strip()
    
    if pitcher:
        current_np = int(score_data.get("np") or 0)
        pitcher_stats[pitcher] = {"np": current_np}

    if batter:
        pa_list = score_data.get("batter_pa_recent") or []
        if isinstance(pa_list, list):
            batter_stats[batter] = {"batter_pa_recent": pa_list}

    save_json(PITCHER_STATS_FILE, pitcher_stats)
    save_json(BATTER_STATS_FILE, batter_stats)


# ================= Routes =================
@app.route('/')
def index():
    return render_template('index.html', data=score_data)

@app.route('/fullboard')
def fullboard():
    return render_template('full_board.html', data=score_data, players_by_team=PLAYERS_BY_TEAM)

@app.route('/admin')
def admin():
    current_players = load_players_from_csv(CSV_PATH)
    return render_template('admin.html', data=score_data, players_by_team=current_players)


# ================= Socket Events =================
core_version = 0

@socketio.on('update')
def handle_update(payload):
    global core_version

    # 判斷是不是純 timer 更新（timer 更新不應該影響核心版本號）
    timer_keys = {"timer_str", "timer_alert"}
    is_only_timer = set(payload.keys()) <= timer_keys

    # 如果不是純 timer → 核心資料更新 → 提升版本號
    if not is_only_timer:
        core_version += 1

    # 把版本號放進 payload
    payload["core_version"] = core_version

    # 廣播給所有 scoreboard client
    socketio.emit("update", payload)


@socketio.on("get_player_stats")
def handle_get_player_stats(data):
    """
    前端切換投手 / 打者時呼叫：
    data = { "pitcher": "王小明", "batter": "張三" }
    """
    p_name = (data or {}).get("pitcher") or ""
    b_name = (data or {}).get("batter") or ""

    resp = {}
    if p_name:
        resp["pitcher"] = p_name
        resp["np"] = int(pitcher_stats.get(p_name, {}).get("np", 0))

    if b_name:
        resp["batter"] = b_name
        resp["batter_pa_recent"] = batter_stats.get(b_name, {}).get("batter_pa_recent", [])

    emit("player_stats", resp)


@socketio.on("save_pitcher_state")
def handle_save_pitcher_state(data):
    """
    存投手 NP： data = { "pitcher": "王小明", "np": 35 }
    """
    global pitcher_stats
    name = (data or {}).get("pitcher") or ""
    if not name:
        return

    try:
        np_val = int(data.get("np") or 0)
    except (TypeError, ValueError):
        np_val = 0

    current = pitcher_stats.get(name, {})
    current["np"] = np_val
    pitcher_stats[name] = current
    save_json(PITCHER_STATS_FILE, pitcher_stats)
    print(f"[INFO] save_pitcher_state: {name} NP={np_val}")


@socketio.on("save_batter_state")
def handle_save_batter_state(data):
    """
    存打者打席紀錄：
    data = { "batter": "張三", "batter_pa_recent": [ {inning:'1上', result:'1B'}, ... ] }
    """
    global batter_stats
    name = (data or {}).get("batter") or ""
    if not name:
        return

    history = data.get("batter_pa_recent") or []
    # 只保留最後 10 筆，避免無限制變大
    if isinstance(history, list):
        history = history[-10:]

    batter_stats[name] = {"batter_pa_recent": history}
    save_json(BATTER_STATS_FILE, batter_stats)
    print(f"[INFO] save_batter_state: {name} PA={len(history)}")

if __name__ == '__main__':
    port = 5000
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        while True:
            try:
                s.bind(('127.0.0.1', port))
                break
            except OSError:
                port += 1

    print(f"Server running on http://127.0.0.1:{port}")
    print(f"Admin Console: http://127.0.0.1:{port}/admin")
    socketio.run(app, host='0.0.0.0', port=port)