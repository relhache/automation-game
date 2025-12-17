import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dhl_final_simple'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- QUESTIONS ---
QUESTIONS = [
    {"id": 1, "text": "Products have uniform dimensions (Standard boxes)", "target": 0, "ans_text": "IDEAL (Uniform)", "exp": "Good! Uniformity is easy for robots."},
    {"id": 2, "text": "We sell fragile glass items and loose eggs", "target": 100, "ans_text": "CHALLENGING (Fragile)", "exp": "Challenging. Requires complex, expensive grippers."},
    {"id": 3, "text": "Annual seasonality is very low (Even throughput)", "target": 0, "ans_text": "IDEAL (Steady)", "exp": "Good! Automation hates idle time."},
    {"id": 4, "text": "High mix of large, small, and heavy items", "target": 100, "ans_text": "CHALLENGING (High Mix)", "exp": "Challenging. Hard to find one machine for all sizes."},
    {"id": 5, "text": "Barcodes are uniform and always readable", "target": 0, "ans_text": "IDEAL (Clean Data)", "exp": "Good! Vision systems need clean data."},
    {"id": 6, "text": "Sporadic growth (Unpredictable future)", "target": 100, "ans_text": "CHALLENGING (Unpredictable)", "exp": "Challenging. ROI calculation is risky."},
    {"id": 7, "text": "Single dispatch type: Parcel only", "target": 0, "ans_text": "IDEAL (Parcel Only)", "exp": "Good! Simple logic for sorting."},
    {"id": 8, "text": "High Value Added Services (Gift wrap, ironing)", "target": 100, "ans_text": "CHALLENGING (VAS)", "exp": "Challenging. Humans are better at custom tasks."},
    {"id": 9, "text": "Low number of SKU types (Low variation)", "target": 0, "ans_text": "IDEAL (Low SKU)", "exp": "Good! Less complexity."},
    {"id": 10, "text": "Items arrive without barcodes or security tags", "target": 100, "ans_text": "CHALLENGING (No Data)", "exp": "Challenging. Needs manual prep before automation."},
    {"id": 11, "text": "Steady future growth forecast", "target": 0, "ans_text": "IDEAL (Steady Growth)", "exp": "Good! Justifies the CapEx investment."},
    {"id": 12, "text": "Extreme peaks (Black Friday is 10x normal)", "target": 100, "ans_text": "CHALLENGING (Peaks)", "exp": "Challenging. Overpaying for capacity used only 1 week."},
    {"id": 13, "text": "Uniform packing standards (Same box sizes)", "target": 0, "ans_text": "IDEAL (Standard Pack)", "exp": "Good! Predictable stacking."},
    {"id": 14, "text": "Multiple dispatch avenues (Parcel + Pallet + C&C)", "target": 100, "ans_text": "CHALLENGING (Mixed Channel)", "exp": "Challenging. Requires mixed workflows."},
    {"id": 15, "text": "Low product weight", "target": 0, "ans_text": "IDEAL (Lightweight)", "exp": "Good! Faster, cheaper robots."},
    {"id": 16, "text": "Heavy products (>25kg)", "target": 100, "ans_text": "CHALLENGING (Heavy)", "exp": "Challenging. Safety risks and slow machinery."},
    {"id": 17, "text": "Low packing media types (Only 1-2 box types)", "target": 0, "ans_text": "IDEAL (Few Boxes)", "exp": "Good! Simplified inventory."},
    {"id": 18, "text": "Ununiformed product barcoding (Random stickers)", "target": 100, "ans_text": "CHALLENGING (Bad Labels)", "exp": "Challenging. Scanners miss them."},
    {"id": 19, "text": "Multiple INDEPENDENT order dispatch from different pick areas", "target": 0, "ans_text": "IDEAL (Pick Areas)", "exp": "Good! Conveyors can merge these easily."},
    {"id": 20, "text": "Consolidated order to customer from all pick areas", "target": 100, "ans_text": "CHALLENGING (Consolidation)", "exp": "Challenging. Complex synchronization needed."},
    {"id": 21, "text": "Low product cube (Small items)", "target": 0, "ans_text": "IDEAL (Small Cube)", "exp": "Good! High density storage possible."},
    {"id": 22, "text": "Multiple packing sizes needed", "target": 100, "ans_text": "CHALLENGING (Multi Pack)", "exp": "Challenging. Machine changeover takes time."},
    {"id": 23, "text": "Low or no Product VAS requirement", "target": 0, "ans_text": "IDEAL (No VAS)", "exp": "Good! Pick -> Pack -> Ship."},
    {"id": 24, "text": "Fashion + Food + General Merch (High Mix)", "target": 100, "ans_text": "CHALLENGING (Contamination)", "exp": "Challenging. Cross-contamination issues."},
    {"id": 25, "text": "High Volume, Low Variation (The Dream)", "target": 0, "ans_text": "IDEAL (The Dream)", "exp": "Good! The perfect scenario for automation."}
]

# --- STATE ---
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
    name = data.get('name', 'Anonymous')
    players[request.sid] = {'name': name, 'score': 0, 'streak': 0}
    emit('wait_screen', {'msg': f"Welcome {name}! Waiting for host..."}, to=request.sid)
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

    # SERVER AUTOMATION: 12s + 2s buffer
    eventlet.sleep(14) 
    
    # AUTO-REVEAL & SCORING
    evaluate_round()

def evaluate_round():
    q = QUESTIONS[current_q_index]
    target = int(q['target'])
    
    # Correct & Fastest Logic
    correct_sids = []
    for sid, ans in answers.items():
        if int(ans['val']) == target:
            correct_sids.append({'sid': sid, 'time': ans['time']})
            
    fastest_sid = None
    if correct_sids:
        correct_sids.sort(key=lambda x: x['time'])
        fastest_sid = correct_sids[0]['sid']

    # Update Scores for ALL connected players
    for sid in players:
        points = 0
        streak_bonus = False
        is_correct = False
        is_fastest = False
        
        if sid in answers:
            if int(answers[sid]['val']) == target:
                is_correct = True
                points = 100
                if sid == fastest_sid:
                    points += 10
                    is_fastest = True
        
        if is_correct:
            players[sid]['streak'] += 1
            if players[sid]['streak'] == 3:
                points += 5
                players[sid]['streak'] = 0 
                streak_bonus = True
        else:
            players[sid]['streak'] = 0
            
        players[sid]['score'] += points
        
        emit('feedback', {
            'correct': is_correct,
            'is_fastest': is_fastest,
            'points': points,
            'streak_bonus': streak_bonus,
            'correct_text': q['ans_text'],
            'explanation': q['exp']
        }, to=sid)

    # Host Update
    emit('host_round_end', {
        'correct_text': q['ans_text']
    }, broadcast=True)

    # Auto Leaderboard at Q12 and Q25
    q_num = current_q_index + 1
    if q_num == 12 or q_num == 25:
        is_winner = (q_num == 25)
        eventlet.sleep(3)
        emit('show_leaderboard_all', {
            'leaderboard': sorted_leaderboard()[:6],
            'is_winner': is_winner
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

@socketio.on('submit_answer')
def handle_answer(data):
    if request.sid not in players: return
    time_taken = time.time() - question_start_time
    if time_taken > 15: return 
    
    val = int(data['value'])
    answers[request.sid] = {'val': val, 'time': time_taken}
    update_host_stats()

def update_host_stats():
    player_names = [p['name'] for p in players.values()]
    
    # CALCULATE VOTES (Ideal vs Challenging)
    ideal_count = 0
    challenging_count = 0
    for a in answers.values():
        if a['val'] == 0: ideal_count += 1
        elif a['val'] == 100: challenging_count += 1
    
    emit('update_stats', {
        'count': len(players), 
        'answers': len(answers), 
        'names': player_names,
        'votes': {'ideal': ideal_count, 'challenging': challenging_count}
    }, broadcast=True)

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

def sorted_leaderboard():
    lb = [{'name': p['name'], 'score': p['score']} for p in players.values()]
    return sorted(lb, key=lambda x: x['score'], reverse=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
