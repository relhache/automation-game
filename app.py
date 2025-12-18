import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import time
import random

app = Flask(__name__)
app.config["SECRET_KEY"] = "dhl_bulletproof_v15"

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*")

# ----------------------------
# CONFIG
# ----------------------------
ROUND_SECONDS = 10          # REQUIRED: round duration is exactly 10s
EVAL_BUFFER_SECONDS = 1.5   # small buffer to let packets arrive (not visible to users)
DISCONNECT_GRACE_SECONDS = 300  # keep player for 5 min for reconnect; then cleanup

HOST_ROOM = "host_room"

# ----------------------------
# QUESTIONS
# ----------------------------
QUESTIONS = [
    {"id": 1, "text": "Products have uniform dimensions (Standard boxes)", "target": 0, "ans_text": "IDEAL (Uniform)", "exp": "Good! Uniformity is easy for robots."},
    {"id": 2, "text": "We sell fragile glass items and wine bottles", "target": 100, "ans_text": "CHALLENGING (Fragile)", "exp": "Challenging. Requires complex, expensive grippers and items can be too fragile."},
    {"id": 3, "text": "Annual seasonality is very low (Even throughput)", "target": 0, "ans_text": "IDEAL (Steady)", "exp": "Good! Automation hates idle time."},
    {"id": 4, "text": "High mix of large, small, and heavy items", "target": 100, "ans_text": "CHALLENGING (High Mix)", "exp": "Challenging. Hard to find one machine for all sizes."},
    {"id": 5, "text": "Barcodes are uniform and always readable", "target": 0, "ans_text": "IDEAL (Clean Data)", "exp": "Good! Vision systems need clean data."},
    {"id": 6, "text": "Sporadic growth (Unpredictable future)", "target": 100, "ans_text": "CHALLENGING (Unpredictable)", "exp": "Challenging. ROI calculation is risky."},
    {"id": 7, "text": "Single dispatch type: Parcel only", "target": 0, "ans_text": "IDEAL (Parcel Only)", "exp": "Good! Simple logic for sorting."},
    {"id": 8, "text": "High Value Added Services (Gift wrap, ironing)", "target": 100, "ans_text": "CHALLENGING (VAS)", "exp": "Challenging. Humans are better at custom tasks."},
    {"id": 9, "text": "Low number of SKU types (Low variation)", "target": 0, "ans_text": "IDEAL (Low SKU)", "exp": "Good! Less complexity."},
    {"id": 10, "text": "Items arrive without barcodes or security tags or with damaged labels", "target": 100, "ans_text": "CHALLENGING (No Data)", "exp": "Challenging. Needs manual prep before automation."},
    {"id": 11, "text": "Steady future growth forecast", "target": 0, "ans_text": "IDEAL (Steady Growth)", "exp": "Good! Justifies the CapEx investment."},
    {"id": 12, "text": "Extreme peaks (Black Friday is 10x normal)", "target": 100, "ans_text": "CHALLENGING (Peaks)", "exp": "Challenging. Overpaying for capacity used only 1 week."},
    {"id": 13, "text": "Uniform packing standards (Same box sizes)", "target": 0, "ans_text": "IDEAL (Standard Pack)", "exp": "Good! Predictable stacking."},
    {"id": 14, "text": "Multiple dispatch avenues (Parcel + Pallet)", "target": 100, "ans_text": "CHALLENGING (Mixed Channel)", "exp": "Challenging. Requires mixed workflows."},
    {"id": 15, "text": "Low product weight", "target": 0, "ans_text": "IDEAL (Lightweight)", "exp": "Good! Faster, cheaper robots."},
    {"id": 16, "text": "Heavy products (>25kg)", "target": 100, "ans_text": "CHALLENGING (Heavy)", "exp": "Challenging. Safety risks and slow machinery."},
    {"id": 17, "text": "Limited number of packing carton sizes (Only 1-2 box types)", "target": 0, "ans_text": "IDEAL (Few Boxes)", "exp": "Good! Simplified inventory."},
    {"id": 18, "text": "High variability in product barcoding and labelling (Random stickers)", "target": 100, "ans_text": "CHALLENGING (Bad Labels)", "exp": "Challenging. Scanners miss them."},
    {"id": 19, "text": "Multiple INDEPENDENT orders dispatched from different pick areas", "target": 0, "ans_text": "IDEAL (Pick Areas)", "exp": "Good! Conveyors can merge these easily."},
    {"id": 20, "text": "Consolidated orders to customer from multiple picking areas", "target": 100, "ans_text": "CHALLENGING (Consolidation)", "exp": "Challenging. Complex synchronization needed."},
    {"id": 21, "text": "Low product cube (Small items)", "target": 0, "ans_text": "IDEAL (Small Cube)", "exp": "Good! High density storage possible."},
    {"id": 22, "text": "Multiple packing sizes needed", "target": 100, "ans_text": "CHALLENGING (Multi Pack)", "exp": "Challenging. Machine changeover takes time."},
    {"id": 23, "text": "Low or no Product VAS requirement", "target": 0, "ans_text": "IDEAL (No VAS)", "exp": "Good! Pick -> Pack -> Ship."},
    {"id": 24, "text": "Fashion + Food + General Merchandise (High Mix)", "target": 100, "ans_text": "CHALLENGING (Contamination)", "exp": "Challenging. Cross-contamination issues."},
    {"id": 25, "text": "High Volume, Low Variation", "target": 0, "ans_text": "IDEAL (The Dream)", "exp": "Good! The perfect scenario for automation."},
]

# ----------------------------
# GAME STATE
# ----------------------------
current_q_index = -1
round_active = False
question_start_time = 0.0
current_round_id = 0

# Players keyed by persistent token:
# players[token] = {
#   "token": str, "sid": str|None, "name": str, "score": int, "streak": int,
#   "connected": bool, "last_seen": float
# }
players = {}

# reverse mapping: sid -> token
sid_to_token = {}

# answers keyed by token: answers[token] = {"val": int, "time": float}
answers = {}

# ----------------------------
# ROUTES
# ----------------------------
@app.route("/")
def index():
    return render_template("player.html")

@app.route("/host")
def host():
    return render_template("host.html")

# ----------------------------
# HELPERS
# ----------------------------
def now_ts() -> float:
    return time.time()

def normalize_name(name: str) -> str:
    return (name or "Anonymous").strip().upper()[:30]

def sorted_leaderboard(limit=None):
    lb = [{"name": p["name"], "score": p["score"]} for p in players.values()]
    lb.sort(key=lambda x: x["score"], reverse=True)
    return lb if limit is None else lb[:limit]

def cleanup_stale_players():
    """Remove players who have been disconnected longer than grace period."""
    cutoff = now_ts() - DISCONNECT_GRACE_SECONDS
    to_delete = []
    for token, p in players.items():
        if not p.get("connected", False) and p.get("last_seen", 0) < cutoff:
            to_delete.append(token)
    for token in to_delete:
        players.pop(token, None)
    if to_delete:
        update_host_stats()

def update_host_stats():
    # only count connected players for host UI
    connected_players = [p for p in players.values() if p.get("connected")]
    connected_count = len(connected_players)

    ideal = 0
    challenging = 0
    for a in answers.values():
        if int(a["val"]) == 0:
            ideal += 1
        elif int(a["val"]) == 100:
            challenging += 1

    # names only for host (privacy)
    names = [p["name"] for p in connected_players]

    emit(
        "update_stats",
        {
            "count": connected_count,
            "answers": len(answers),
            "names": names,
            "votes": {"ideal": ideal, "challenging": challenging},
        },
        to=HOST_ROOM,
    )

def round_timer_task(round_id: int):
    eventlet.sleep(ROUND_SECONDS + EVAL_BUFFER_SECONDS)
    evaluate_round(round_id)

def evaluate_round(round_id: int):
    global round_active

    # Ignore stale timers
    if round_id != current_round_id:
        return
    if not round_active:
        return

    round_active = False

    if current_q_index < 0 or current_q_index >= len(QUESTIONS):
        return

    q = QUESTIONS[current_q_index]
    target = int(q["target"])

    # snapshot answers to avoid mutation during scoring
    answers_snapshot = dict(answers)

    # Identify fastest correct
    correct = []
    for token, ans in answers_snapshot.items():
        try:
            if int(ans["val"]) == target:
                correct.append({"token": token, "time": float(ans["time"])})
        except Exception:
            continue

    fastest_token = None
    if correct:
        correct.sort(key=lambda x: x["time"])
        fastest_token = correct[0]["token"]

    # Score players (including disconnected; emissions only to connected)
    for token, p in list(players.items()):
        try:
            p_name = p["name"]
            points = 0
            streak_bonus = False
            is_correct = False
            is_fastest = False

            if token in answers_snapshot:
                player_val = int(answers_snapshot[token]["val"])
                if player_val == target:
                    is_correct = True
                    points = 100
                    if token == fastest_token:
                        points += 30
                        is_fastest = True

            if is_correct:
                p["streak"] += 1
                if p["streak"] == 3:
                    points += 20
                    p["streak"] = 0
                    streak_bonus = True
            else:
                p["streak"] = 0

            p["score"] += points

            # feedback message
            if is_correct:
                options = [
                    f"Well done {p_name}.",
                    f"Strong call, {p_name}.",
                    f"Nice one, {p_name}.",
                    f"Automation instincts on point, {p_name}.",
                    f"Good read, {p_name}.",
                ]
            else:
                options = [
                    f"Not this time, {p_name}.",
                    f"Close—stay sharp, {p_name}.",
                    f"Good effort, {p_name}.",
                    f"Next one is yours, {p_name}.",
                    f"Keep going, {p_name}.",
                ]
            feedback_msg = random.choice(options)

            # send feedback only if connected and has sid
            if p.get("connected") and p.get("sid"):
                emit(
                    "feedback",
                    {
                        "correct": is_correct,
                        "is_fastest": is_fastest,
                        "points": points,
                        "streak_bonus": streak_bonus,
                        "correct_text": q["ans_text"],
                        "explanation": q["exp"],
                        "random_msg": feedback_msg,
                    },
                    to=p["sid"],
                )
        except Exception as e:
            print(f"Error scoring/sending feedback for token {token}: {e}")

    # Host reveal (host only)
    emit(
        "host_round_end",
        {"correct_text": q["ans_text"], "explanation": q["exp"]},
        to=HOST_ROOM,
    )

    # Leaderboard checkpoints (broadcast to all clients)
    q_num = current_q_index + 1
    if q_num == 12 or q_num == 25:
        is_winner = (q_num == 25)
        eventlet.sleep(1)
        emit(
            "show_leaderboard_all",
            {"leaderboard": sorted_leaderboard(limit=6), "is_winner": is_winner},
            broadcast=True,
        )

    update_host_stats()

# ----------------------------
# SOCKET EVENTS
# ----------------------------
@socketio.on("join_host")
def handle_join_host(_data=None):
    join_room(HOST_ROOM)
    update_host_stats()

@socketio.on("join_game")
def handle_join_game(data):
    # token-based identity (no name collisions)
    sid = request.sid
    token = (data or {}).get("token", "").strip()
    name = normalize_name((data or {}).get("name", ""))

    if not token:
        # refuse silent invalid joins
        emit("wait_screen", {"msg": "Missing token. Please refresh."}, to=sid)
        return

    # If token exists, reconnect. If not, create.
    if token not in players:
        players[token] = {
            "token": token,
            "sid": sid,
            "name": name,
            "score": 0,
            "streak": 0,
            "connected": True,
            "last_seen": now_ts(),
        }
        print(f"NEW PLAYER: {name} ({token})")
    else:
        # reconnect/update
        players[token]["sid"] = sid
        players[token]["connected"] = True
        players[token]["last_seen"] = now_ts()
        # If user changed name, update (optional, keep normalized)
        if name:
            players[token]["name"] = name
        print(f"RECONNECTED: {players[token]['name']} ({token})")

    sid_to_token[sid] = token

    emit("wait_screen", {"msg": f"Welcome {players[token]['name']}! Waiting for host..."}, to=sid)
    cleanup_stale_players()
    update_host_stats()

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    token = sid_to_token.pop(sid, None)
    if token and token in players:
        players[token]["connected"] = False
        players[token]["sid"] = None
        players[token]["last_seen"] = now_ts()
        print(f"DISCONNECT: {players[token]['name']} ({token})")
        cleanup_stale_players()
        update_host_stats()

@socketio.on("host_start_q")
def start_question(_data=None):
    global current_q_index, question_start_time, answers, round_active, current_round_id

    cleanup_stale_players()

    if round_active:
        return
    if current_q_index >= len(QUESTIONS) - 1:
        return

    current_q_index += 1
    q = QUESTIONS[current_q_index]

    answers = {}
    question_start_time = now_ts()
    round_active = True
    current_round_id += 1
    round_id = current_round_id

    # Broadcast question to everyone (host + players)
    emit(
        "new_question",
        {"q_id": current_q_index + 1, "text": q["text"], "duration": ROUND_SECONDS},
        broadcast=True,
    )

    update_host_stats()

    # background evaluation (non-blocking)
    socketio.start_background_task(round_timer_task, round_id)

@socketio.on("submit_answer")
def handle_answer(data):
    global answers

    sid = request.sid
    token = sid_to_token.get(sid)
    if not token or token not in players:
        return
    if not round_active:
        return

    # enforce server truth: accept answers only within ROUND_SECONDS
    time_taken = now_ts() - question_start_time
    if time_taken < 0 or time_taken > ROUND_SECONDS:
        return

    try:
        val = int((data or {}).get("value"))
        if val not in (0, 100):
            return
        answers[token] = {"val": val, "time": float(time_taken)}
        update_host_stats()
    except Exception:
        return

@socketio.on("host_trigger_leaderboard")
def trigger_leaderboard():
    is_winner = (current_q_index >= 24)
    emit(
        "show_leaderboard_all",
        {"leaderboard": sorted_leaderboard(limit=6), "is_winner": is_winner},
        broadcast=True,
    )

@socketio.on("host_hide_leaderboard")
def hide_leaderboard():
    emit("hide_leaderboard_all", {}, broadcast=True)

@socketio.on("host_reset_game")
def reset_game():
    global current_q_index, players, answers, round_active, current_round_id
    current_q_index = -1
    answers = {}
    players = {}
    sid_to_token.clear()
    round_active = False
    current_round_id += 1  # invalidate any running timer tasks

    emit("force_reload", {}, broadcast=True)
    emit("reset_confirm", {}, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, debug=True)
