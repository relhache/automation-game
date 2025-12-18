import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import time
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dhl_bulletproof_v15_final'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- QUESTIONS ---
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
    {"id": 25, "text": "High Volume, Low Variation", "target": 0, "ans_text": "IDEAL (The Dream)", "exp": "Good! The perfect scenario for automation."}
]

# --- GAME STATE ---
current_q_index = -1 
players = {} 
answers = {} 
question_start_time = 0

@app.route('/')
def index():
    return render_template('player.html')

@app.route('/host')
def host():
    return render_template('host.html')

# --- SOCKET EVENTS ---

@socketio.on('join_game')
def handle_join(data):
    # AUTO-RECOVERY: If player disconnects, reconnect them to their old score
    new_sid = request.sid
    name = data.get('name', 'Anonymous').strip().upper()
    
    existing_sid = None
    for sid, p_data in players.items():
        if p_data['name'] == name:
            existing_sid = sid
            break
    
    if existing_sid:
        # Transfer data to new connection
        old_data = players[existing_sid]
        players[new_sid] = old_data
        del players[existing_sid]
        print(f"RECOVERED: {name}")
    else:
        # New Player
        players[new_sid] = {'name': name, 'score': 0, 'streak': 0}

    emit('wait_screen', {'msg': f"Welcome {name}! Waiting for host..."}, to=new_sid)
    update_host_stats()

@socketio.on('host_start_q')
def start_question(data):
    global current_q_index, question_start_time, answers
    
    if current_q_index >= len(QUESTIONS) - 1:
        return

    current_q_index += 1
    q = QUESTIONS[current_q_index]
    answers = {} 
    question_start_time = time.time()
    
    emit('new_question', {
        'q_id': current_q_index + 1,
        'text': q['text'],
        'duration': 12
    }, broadcast=True)
    
    update_host_stats()

    # SERVER TIMER
    eventlet.sleep(14) 
    
    # TRIGGER RESULTS
    evaluate_round()

def evaluate_round():
    q = QUESTIONS[current_q_index]
    target = int(q['target'])
    
    # 1. Identify Correct & Fastest
    correct_sids = []
    
    # Safe iteration over answers
    for sid, ans in list(answers.items()):
        try:
            val = int(ans['val'])
            if val == target:
                correct_sids.append({'sid': sid, 'time': ans['time']})
        except:
            continue
            
    fastest_sid = None
    if correct_sids:
        correct_sids.sort(key=lambda x: x['time'])
        fastest_sid = correct_sids[0]['sid']

    # 2. Score Every Player (Safe Snapshot Loop)
    # Using list(players.keys()) prevents "RuntimeError" if a player disconnects mid-loop
    for sid in list(players.keys()):
        try:
            p_name = players[sid]['name']
            points = 0
            streak_bonus = False
            is_correct = False
            is_fastest = False
            
            if sid in answers:
                player_val = int(answers[sid]['val'])
                
                if player_val == target:
                    is_correct = True
                    points = 100
                    if sid == fastest_sid:
                        points += 30
                        is_fastest = True
            
            # Streak Logic
            if is_correct:
                players[sid]['streak'] += 1
                if players[sid]['streak'] == 3:
                    points += 20
                    players[sid]['streak'] = 0 
                    streak_bonus = True
            else:
                players[sid]['streak'] = 0
                
            players[sid]['score'] += points
            
            # GENDER NEUTRAL RANDOM MESSAGES
            feedback_msg = ""
            if is_correct:
                options = [
                    f"Good Job {p_name}!",
                    f"You are a rockstar {p_name}!",
                    f"Are you interested to move to the Automation team {p_name}?",
                    "Someone knows their automation 😉", # Neutral
                    "Look at you 😃 you Automation Expert!"
                ]
                feedback_msg = random.choice(options)
            else:
                options = [
                    f"Bad job {p_name}!",
                    f"Focus {p_name}!",
                    f"Apparently you need this Automation Training {p_name}",
                    f"Better Ask Andreas {p_name}",
                    "What a disappointment!"
                ]
                feedback_msg = random.choice(options)

            emit('feedback', {
                'correct': is_correct,
                'is_fastest': is_fastest,
                'points': points,
                'streak_bonus': streak_bonus,
                'correct_text': q['ans_text'],
                'explanation': q['exp'],
                'random_msg': feedback_msg
            }, to=sid)
            
        except Exception as e:
            # If a player dropped connection completely, skip them safely
            print(f"Skipping disconnected player {sid}")
            continue

    # 3. Update Host
    emit('host_round_end', {
        'correct_text': q['ans_text'],
        'explanation': q['exp'] 
    }, broadcast=True)

    # 4. Auto-Leaderboard (Q12 & Q25)
    q_num = current_q_index + 1
    if q_num == 12 or q_num == 25:
        is_winner = (q_num == 25)
        eventlet.sleep(3)
        emit('show_leaderboard_all', {
            'leaderboard': sorted_leaderboard()[:6],
            'is_winner': is_winner
        }, broadcast=True)

@socketio.on('submit_answer')
def handle_answer(data):
    if request.sid not in players: return
    time_taken = time.time() - question_start_time
    if time_taken > 15: return 
    
    try:
        val = int(data['value'])
        answers[request.sid] = {'val': val, 'time': time_taken}
        update_host_stats()
    except:
        pass

def update_host_stats():
    ideal = 0
    challenging = 0
    for a in answers.values():
        if int(a['val']) == 0: ideal += 1
        elif int(a['val']) == 100: challenging += 1

    player_names = [p['name'] for p in players.values()]
    
    emit('update_stats', {
        'count': len(players), 
        'answers': len(answers), 
        'names': player_names,
        'votes': {'ideal': ideal, 'challenging': challenging}
    }, broadcast=True)

@socketio.on('host_trigger_leaderboard')
def trigger_leaderboard():
    is_winner = (current_q_index >= 24)
    emit('show_leaderboard_all', {
        'leaderboard': sorted_leaderboard()[:6],
        'is_winner': is_winner
    }, broadcast=True)

@socketio.on('host_hide_leaderboard')
def hide_leaderboard():
    emit('hide_leaderboard_all', {}, broadcast=True)

@socketio.on('host_reset_game')
def reset_game():
    global current_q_index, players, answers
    current_q_index = -1
    answers = {}
    players = {}
    # Kick everyone to login
    emit('force_reload', {}, broadcast=True)
    emit('reset_confirm', {}, broadcast=True)

def sorted_leaderboard():
    lb = [{'name': p['name'], 'score': p['score']} for p in players.values()]
    return sorted(lb, key=lambda x: x['score'], reverse=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
