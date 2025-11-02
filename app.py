import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import socket

app = Flask(__name__, template_folder='templates') # 指定 templates 資料夾
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# 初始化計分板資料，包含所有欄位和初始值
score_data = {
    "away_team": "G",     # 客隊隊名縮寫
    "home_team": "B",     # 主隊隊名縮寫
    "away_logo_url": "",  # 客隊 Logo URL/路徑
    "home_logo_url": "",  # 主隊 Logo URL/路徑
    "away_score": 0,
    "home_score": 0,
    "inning": "1上",      # 局數 (4 ▽)
    "pitcher": "Shohei Ohtani",   # 投手
    "batter": "9 大谷翔平", # 打者 (包含棒次/背號)
    "np": 0,              # 投球數
    "avg": ".292",        # 打擊率
    "balls": 0,           # 壞球 (B)
    "strikes": 0,         # 好球 (S)
    "outs": 0,            # 出局 (O)
    "bases": [False, False, False] # [一壘, 二壘, 三壘]
}

@app.route('/')
def index():
    # 將資料傳遞給 index.html 模板
    return render_template('index.html', data=score_data)

@app.route('/admin')
def admin():
    # 將資料傳遞給 admin.html 模板，用於填充初始值
    return render_template('admin.html', data=score_data)

@socketio.on('update')
def handle_update(data):
    # 更新計分板資料
    score_data.update(data)
    
    # 向所有客戶端廣播更新後的資料
    emit('update', score_data, broadcast=True)

if __name__ == '__main__':
    # 端口自動增量邏輯，從 5000 開始找可用端口
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
    
    # 啟動 SocketIO 伺服器
    socketio.run(app, host='0.0.0.0', port=port)