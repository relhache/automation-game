from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GAME DATA ---
# Add your questions here. Target is the "correct" percentage (0-100).
QUESTIONS = [
    {"id": 1, "text": "High SKU Variability (Items look very different)", "target": 20, "left_label": "Manual", "right_label": "Automate"},
    {"id": 2, "text": "High Volume, Low Variation (Picking the same box 10k times)", "target": 90, "left_label": "Manual", "right_label": "Automate"},
    {"id": 3, "text": "Fragile Items (Glass/Eggs)", "target": 30, "left_label": "Manual", "right_label": "Automate"},
]

current_question_index = 0
player_answers = {} # Stores answers for the current question

@app.route('/')
def index():
    return render_template('player.html')

@app.route('/host')
def host():
    return render_template('host.html')

# --- SOCKET EVENTS ---

@socketio.on('connect')
def on_connect():
    # When a player connects, send them the current question state
    emit('new_question', QUESTIONS[current_question_index])

@socketio.on('submit_answer')
def handle_answer(data):
    # Store player answer
    player_id = request.sid
    value = int(data['value'])
    player_answers[player_id] = value
    
    # Calculate stats to show Host
    count = len(player_answers)
    avg_val = sum(player_answers.values()) / count
    
    # Send update to Host only
    emit('update_stats', {'count': count, 'average': avg_val}, broadcast=True, include_self=False)

@socketio.on('next_question')
def next_question():
    global current_question_index, player_answers
    
    if current_question_index < len(QUESTIONS) - 1:
        current_question_index += 1
        player_answers = {} # Reset answers for new round
        
        # Broadcast new question to EVERYONE (Host + Players)
        emit('new_question', QUESTIONS[current_question_index], broadcast=True)
        # Reset host stats
        emit('reset_stats', {}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
