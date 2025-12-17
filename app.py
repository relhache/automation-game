from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'automation_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 25 CUSTOM QUESTIONS ---
# Target 0 = Good Fit/Automate (Left)
# Target 100 = Challenging/Manual (Right)
QUESTIONS = [
    # --- BATCH 1 (Q1-Q12) ---
    {"id": 1, "text": "Products have uniform dimensions (Standard boxes)", "target": 0, "exp": "Good! Uniformity is easy for robots."},
    {"id": 2, "text": "We sell fragile glass items and loose eggs", "target": 100, "exp": "Challenging. Requires complex, expensive grippers."},
    {"id": 3, "text": "Annual seasonality is very low (Even throughput)", "target": 0, "exp": "Good! Automation hates idle time."},
    {"id": 4, "text": "High mix of large, small, and heavy items", "target": 100, "exp": "Challenging. Hard to find one machine for all sizes."},
    {"id": 5, "text": "Barcodes are uniform and always readable", "target": 0, "exp": "Good! Vision systems need clean data."},
    {"id": 6, "text": "Sporadic growth (Unpredictable future)", "target": 100, "exp": "Challenging. ROI calculation is risky."},
    {"id": 7, "text": "Single dispatch type: Parcel only", "target": 0, "exp": "Good! Simple logic for sorting."},
    {"id": 8, "text": "High Value Added Services (Gift wrap, ironing)", "target": 100, "exp": "Challenging. Humans are better at custom tasks."},
    {"id": 9, "text": "Low number of SKU types (Low variation)", "target": 0, "exp": "Good! Less complexity."},
    {"id": 10, "text": "Items arrive without barcodes or security tags", "target": 100, "exp": "Challenging. Needs manual prep before automation."},
    {"id": 11, "text": "Steady future growth forecast", "target": 0, "exp": "Good! Justifies the CapEx investment."},
    {"id": 12, "text": "Extreme peaks (Black Friday is 10x normal)", "target": 100, "exp": "Challenging. You overpay for capacity used only 1 week."},
    
    # --- BATCH 2 (Q13-Q25) ---
    {"id": 13, "text": "Uniform packing standards (Same box sizes)", "target": 0, "exp": "Good! Predictable stacking."},
    {"id": 14, "text": "Multiple dispatch avenues (Parcel + Pallet + Click&Collect)", "target": 100, "exp": "Challenging. Requires mixed workflows."},
    {"id": 15, "text": "Low product weight", "target": 0, "exp": "Good! Faster, cheaper robots."},
    {"id": 16, "text": "Heavy products (>25kg)", "target": 100, "exp": "Challenging. Safety risks and slow machinery."},
    {"id": 17, "text": "Low packing media types (Only 1-2 box types)", "target": 0, "exp": "Good! Simplified inventory."},
    {"id": 18, "text": "Ununiformed product barcoding (Stickers in random places)", "target": 100, "exp": "Challenging. Scanners miss them."},
    {"id": 19, "text": "Multiple order dispatch from different pick areas", "target": 0, "exp": "Good! Conveyors can merge these easily."},
    {"id": 20, "text": "Consolidated order to customer from all pick areas", "target": 100, "exp": "Challenging. Complex synchronization needed."},
    {"id": 21, "text": "Low product cube (Small items)", "target": 0, "exp": "Good! High density storage possible."},
    {"id": 22, "text": "Multiple packing sizes needed", "target": 100, "exp": "Challenging. Machine changeover takes time."},
    {"id": 23, "text": "Low or no Product VAS requirement", "target": 0, "exp": "Good! Pick -> Pack -> Ship."},
    {"id": 24, "text": "Fashion + Food + General Merch (High Mix)", "target": 100, "exp": "Challenging. Cross-contamination and temp control issues."},
    {"id": 25, "text": "High Volume, Low Variation (The Dream)", "target": 0, "exp": "Good! The perfect scenario for automation."}
]

# --- GLOBAL GAME STATE ---
current_q_index = -1 
players = {} # {sid: {'name': 'John', 'score': 0}}
answers = {} # {sid: {'val': 50, 'time': 1.2}}
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
    players[request.sid] = {'name': name, 'score': 0}
    emit('wait_screen', {'msg': f"Welcome {name}! Waiting for host..."}, to=request.sid)
    emit('update_player_count', {'count': len(players)}, broadcast=True)

@socketio.on('host_start_q')
def start_question(data):
    global current_q_index, question_start_time, answers
    
    if current_q_index >= len(QUESTIONS) - 1:
        emit('game_over', sorted_leaderboard()[:5], broadcast=True)
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

@socketio.on('submit_answer')
def handle_answer(data):
    if request.sid not in players: return
    
    # Calculate time taken
    time_taken = time.time() - question_start_time
    if time_taken > 13: return # Late buffer
    
    val = int(data['value'])
    answers[request.sid] = {'val': val, 'time': time_taken}

@socketio.on('host_show_results')
def show_results():
    global players
    q = QUESTIONS[current_q_index]
    target = q['target']
    
    # 1. Identify Correct Players
    correct_players = []
    
    for sid, ans in answers.items():
        user_val = ans['val']
        user_time = ans['time']
        
        # Check correctness (Margin of error logic)
        is_correct = False
        if target == 0 and user_val < 45: is_correct = True
        if target == 100 and user_val > 55: is_correct = True
        
        if is_correct:
            correct_players.append({
                'sid': sid,
                'time': user_time
            })
    
    # 2. Find the Fastest Correct Player
    fastest_sid = None
    if correct_players:
        # Sort by time (ascending) -> first one is fastest
        correct_players.sort(key=lambda x: x['time'])
        fastest_sid = correct_players[0]['sid']

    # 3. Assign Points and Feedback
    for sid in players.keys(): # Loop through all connected players
        points_earned = 0
        is_correct = False
        is_fastest = False
        
        # Check if they answered this round
        if sid in answers:
            user_val = answers[sid]['val']
            # Re-check logic for individual feedback
            if (target == 0 and user_val < 45) or (target == 100 and user_val > 55):
                is_correct = True
                points_earned = 100
                
                # Apply Speed Bonus ONLY to the fastest
                if sid == fastest_sid:
                    points_earned += 10
                    is_fastest = True
        
        # Update Total Score
        players[sid]['score'] += points_earned
        
        # Send Personal Feedback
        emit('feedback', {
            'correct': is_correct,
            'is_fastest': is_fastest,
            'points': points_earned,
            'explanation': q['exp']
        }, to=sid)

    # 4. Send Stats to Host
    emit('host_stats', {
        'correct_count': len(correct_players),
        'total': len(answers),
        'leaderboard': sorted_leaderboard()[:5]
    }, to=request.sid)

def sorted_leaderboard():
    lb = [{'name': p['name'], 'score': p['score']} for p in players.values()]
    return sorted(lb, key=lambda x: x['score'], reverse=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
