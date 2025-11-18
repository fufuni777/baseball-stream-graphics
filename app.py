import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import socket
import csv
from collections import defaultdict
from pathlib import Path

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "team_players.csv"   # 確保是相對 app.py 的路徑

def load_players_from_csv(path: Path):
    players_by_team = defaultdict(list)
    if not path.exists():
        print(f"[WARN] team_players.csv not found at: {path}")
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        print("[DEBUG] CSV fieldnames:", reader.fieldnames)  # ⬅︎ 看看欄位名是什麼

        for row in reader:
            team = (row.get("team") or "").strip()
            name = (row.get("name") or "").strip()
            if not team or not name:
                print("[DEBUG] skip row:", row)  # 有問題的列會印出來
                continue
            players_by_team[team].append(name)

    print("[DEBUG] PLAYERS_BY_TEAM =", dict(players_by_team))
    return dict(players_by_team)

PLAYERS_BY_TEAM = load_players_from_csv(CSV_PATH)

score_data = {
    "away_team": "G",
    "home_team": "B",
    "away_logo_url": "",
    "home_logo_url": "",
    "away_score": 0,
    "home_score": 0,
    "inning": "1上",
    "pitcher": "大谷翔平",
    "batter": "3 王威晨",
    "np": 0,
    "avg": ".292",
    "balls": 0,
    "strikes": 0,
    "outs": 0,
    "bases": [False, False, False]
}

@app.route('/')
def index():
    return render_template('index.html', data=score_data)

@app.route('/admin')
def admin():
    return render_template(
        'admin.html',
        data=score_data,
        players_by_team=PLAYERS_BY_TEAM   # 👈 多傳這個
    )

@socketio.on('update')
def handle_update(data):
    print("[DEBUG] got update:", data)
    score_data.update(data)
    emit('update', score_data, broadcast=True)

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
    print(f"Scoreboard: http://127.0.0.1:{port}/")
    print(f"Admin Console: http://127.0.0.1:{port}/admin")

    socketio.run(app, host='0.0.0.0', port=port)
