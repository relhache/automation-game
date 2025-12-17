import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dhl_autostore_secret'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- 25 CUSTOM QUESTIONS (Safe Format) ---
# Target 0 = IDEAL FOR AUTOMATION (Left)
# Target 100 = CHALLENGING FOR AUTOMATION (Right)
QUESTIONS = [
    {
        "id": 1, 
        "text": "Products have uniform dimensions (Standard boxes)", 
        "target": 0, 
        "ans_text": "IDEAL (Uniform)", 
        "exp": "Good! Uniformity is easy for robots."
    },
    {
        "id": 2, 
        "text": "We sell fragile glass items and loose eggs", 
        "target": 100, 
        "ans_text": "CHALLENGING (Fragile)", 
        "exp": "Challenging. Requires complex, expensive grippers."
    },
    {
        "id": 3, 
        "text": "Annual seasonality is very low (Even throughput)", 
        "target": 0, 
        "ans_text": "IDEAL (Steady)", 
        "exp": "Good! Automation hates idle time."
    },
    {
        "id": 4, 
        "text": "High mix of large, small, and heavy items", 
        "target": 100, 
        "ans_text": "CHALLENGING (High Mix)", 
        "exp": "Challenging. Hard to find one machine for all sizes."
    },
    {
        "id": 5, 
        "text": "Barcodes are uniform and always readable", 
        "target": 0, 
        "ans_text": "IDEAL (Clean Data)", 
        "exp": "Good! Vision systems need clean data."
    },
    {
        "id": 6, 
        "text": "Sporadic growth (Unpredictable future)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Unpredictable)", 
        "exp": "Challenging. ROI calculation is risky."
    },
    {
        "id": 7, 
        "text": "Single dispatch type: Parcel only", 
        "target": 0, 
        "ans_text": "IDEAL (Parcel Only)", 
        "exp": "Good! Simple logic for sorting."
    },
    {
        "id": 8, 
        "text": "High Value Added Services (Gift wrap, ironing)", 
        "target": 100, 
        "ans_text": "CHALLENGING (VAS)", 
        "exp": "Challenging. Humans are better at custom tasks."
    },
    {
        "id": 9, 
        "text": "Low number of SKU types (Low variation)", 
        "target": 0, 
        "ans_text": "IDEAL (Low SKU)", 
        "exp": "Good! Less complexity."
    },
    {
        "id": 10, 
        "text": "Items arrive without barcodes or security tags", 
        "target": 100, 
        "ans_text": "CHALLENGING (No Data)", 
        "exp": "Challenging. Needs manual prep before automation."
    },
    {
        "id": 11, 
        "text": "Steady future growth forecast", 
        "target": 0, 
        "ans_text": "IDEAL (Steady Growth)", 
        "exp": "Good! Justifies the CapEx investment."
    },
    {
        "id": 12, 
        "text": "Extreme peaks (Black Friday is 10x normal)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Peaks)", 
        "exp": "Challenging. Overpaying for capacity used only 1 week."
    },
    {
        "id": 13, 
        "text": "Uniform packing standards (Same box sizes)", 
        "target": 0, 
        "ans_text": "IDEAL (Standard Pack)", 
        "exp": "Good! Predictable stacking."
    },
    {
        "id": 14, 
        "text": "Multiple dispatch avenues (Parcel + Pallet + C&C)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Mixed Channel)", 
        "exp": "Challenging. Requires mixed workflows."
    },
    {
        "id": 15, 
        "text": "Low product weight", 
        "target": 0, 
        "ans_text": "IDEAL (Lightweight)", 
        "exp": "Good! Faster, cheaper robots."
    },
    {
        "id": 16, 
        "text": "Heavy products (>25kg)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Heavy)", 
        "exp": "Challenging. Safety risks and slow machinery."
    },
    {
        "id": 17, 
        "text": "Low packing media types (Only 1-2 box types)", 
        "target": 0, 
        "ans_text": "IDEAL (Few Boxes)", 
        "exp": "Good! Simplified inventory."
    },
    {
        "id": 18, 
        "text": "Ununiformed product barcoding (Random stickers)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Bad Labels)", 
        "exp": "Challenging. Scanners miss them."
    },
    {
        "id": 19, 
        "text": "Multiple order dispatch from different pick areas", 
        "target": 0, 
        "ans_text": "IDEAL (Pick Areas)", 
        "exp": "Good! Conveyors can merge these easily."
    },
    {
        "id": 20, 
        "text": "Consolidated order to customer from all pick areas", 
        "target": 100, 
        "ans_text": "CHALLENGING (Consolidation)", 
        "exp": "Challenging. Complex synchronization needed."
    },
    {
        "id": 21, 
        "text": "Low product cube (Small items)", 
        "target": 0, 
        "ans_text": "IDEAL (Small Cube)", 
        "exp": "Good! High density storage possible."
    },
    {
        "id": 22, 
        "text": "Multiple packing sizes needed", 
        "target": 100, 
        "ans_text": "CHALLENGING (Multi Pack)", 
        "exp": "Challenging. Machine changeover takes time."
    },
    {
        "id": 23, 
        "text": "Low or no Product VAS requirement", 
        "target": 0, 
        "ans_text": "IDEAL (No VAS)", 
        "exp": "Good! Pick -> Pack -> Ship."
    },
    {
        "id": 24, 
        "text": "Fashion + Food + General Merch (High Mix)", 
        "target": 100, 
        "ans_text": "CHALLENGING (Contamination)", 
        "exp": "Challenging. Cross-contamination issues."
    },
    {
        "id": 25, 
        "text": "High Volume, Low Variation (The Dream)", 
        "target": 0, 
        "ans_text": "IDEAL (The Dream)", 
        "exp": "Good! The perfect scenario for automation."
    }
]

# --- GLOBAL GAME STATE ---
current_q_index = -1 
players = {} # {sid: {'name': 'Name', 'score': 0, 'streak': 0}}
answers = {} 
question_start_time = 0

@app.route('/')
def index():
    return render_template('player.html')

# SECURE HOST URL
@app.route('/dhl_secure_manager')
def host():
    return render_template('host.html')

# --- SOCKET EVENTS ---

@socketio.on('join_game')
def handle_join(data):
    name = data.get('name', 'Anonymous')
    players[request.sid] = {'name': name, 'score': 0, 'streak': 0}
    emit('wait_screen', {'msg': f"Welcome {name}! Waiting for host..."}, to=request.sid)
    # Send full player list to host
    player_list = [p['name'] for p in players.values()]
    emit('update_player_stats', {'count': len(players), 'answers': len(answers), 'names': player_list}, broadcast=True)

@socketio.on('host_start_q')
def start_question(data):
    global current_q_index, question_start_time, answers
    
    if current_q_index >= len(QUESTIONS) - 1:
        emit('game_over', sorted_leaderboard()[:6], broadcast=True)
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
    
    player_list = [p['name'] for p in players.values()]
    emit('update_player_stats', {'count': len(players), 'answers': 0, 'names': player_list}, broadcast=True)

@socketio.on('host_reset_game')
def reset_game():
    global current_q_index, players, answers
    current_q_index = -1
    answers = {}
    for sid in players:
        players[sid]['score'] = 0
        players[sid]['streak'] = 0
        emit('wait_screen', {'msg': "Game Reset! Waiting for start..."}, to=sid)
    
    emit('reset_confirm', {}, broadcast=True)

@socketio.on('submit_answer')
def handle_answer(data):
    if request.sid not in players: return
    time_taken = time.time() - question_start_time
    
    # Allow a small buffer for network latency (14s total)
    if time_taken > 14: return 
    
    val = int(data['value'])
    answers[request.sid] = {'val': val, 'time': time_taken}
    
    player_list = [p['name'] for p in players.values()]
    emit('update_player_stats', {'count': len(players), 'answers': len(answers), 'names': player_list}, broadcast=True)

@socketio.on('host_show_results')
def show_results():
    global players
    if current_q_index < 0: return
    q = QUESTIONS[current_q_index]
    target = q['target']
    
    # 1. Identify Correct Players (Strict Binary Check)
    correct_players = []
    for sid, ans in answers.items():
        user_val = ans['val']
        # Slider is binary 0 or 100. Target is 0 or 100. Must match exactly.
        if user_val == target:
            correct_players.append({'sid': sid, 'time': ans['time']})
    
    # 2. Find Fastest
    fastest_sid = None
    if correct_players:
        correct_players.sort(key=lambda x: x['time'])
        fastest_sid = correct_players[0]['sid']

    # 3. Assign Points, Streaks & Feedback
    for sid in players.keys():
        points_earned = 0
        streak_bonus = False
        is_correct = False
        is_fastest = False
        
        if sid in answers:
            user_val = answers[sid]['val']
            if user_val == target:
                is_correct = True
                points_earned = 100
                
                # Fastest Bonus
                if sid == fastest_sid:
                    points_earned += 10
                    is_fastest = True
        
        # Streak Logic (Corrected: 3 in a row = +5 and reset)
        if is_correct:
            players[sid]['streak'] += 1
            if players[sid]['streak'] == 3:
                points_earned += 5
                players[sid]['streak'] = 0 # Reset counter
                streak_bonus = True
        else:
            players[sid]['streak'] = 0 # Missed one, reset streak
            
        players[sid]['score'] += points_earned
        
        emit('feedback', {
            'correct': is_correct,
            'is_fastest': is_fastest,
            'points': points_earned,
            'streak_bonus': streak_bonus,
            'target': target,
            'correct_text': q['ans_text'],
            'explanation': q['exp']
        }, to=sid)

    emit('host_stats', {
        'correct_count': len(correct_players),
        'total': len(answers),
        'correct_text': q['ans_text'],
        'leaderboard': sorted_leaderboard()[:6]
    }, to=request.sid)

def sorted_leaderboard():
    lb = [{'name': p['name'], 'score': p['score']} for p in players.values()]
    return sorted(lb, key=lambda x: x['score'], reverse=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
