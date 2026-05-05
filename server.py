from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import uuid
import json
import os
import hashlib
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-2024')
app.config['DEBUG'] = os.environ.get('DEBUG', 'False').lower() == 'true'

CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=False)

# Хранилище
users = {}
messages = defaultdict(list)
online_users = {}

AVAILABLE_AVATARS = ["😎", "🦊", "🐱", "🐶", "🦁", "🐼", "🐨", "🐸", "🦄", "🐙", "👾", "🤖", "👻", "💀", "👽", "🎃", "🌟", "🔥", "💎", "🍀"]


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_id():
    return str(uuid.uuid4())[:8]


def get_chat_room(u1, u2):
    return f"chat_{'_'.join(sorted([u1, u2]))}"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    avatar = data.get('avatar', '😎')

    if not username or len(username) < 3:
        return jsonify({'error': 'Имя должно быть минимум 3 символа'}), 400
    if not password or len(password) < 4:
        return jsonify({'error': 'Пароль должен быть минимум 4 символа'}), 400

    for u in users.values():
        if u['username'].lower() == username.lower():
            return jsonify({'error': 'Имя уже занято'}), 400

    user_id = generate_id()
    users[user_id] = {
        'username': username,
        'password_hash': hash_password(password),
        'avatar': avatar if avatar in AVAILABLE_AVATARS else '😎',
        'bio': '',
        'friends': [],
        'created_at': datetime.now().isoformat()
    }

    return jsonify({
        'user_id': user_id,
        'username': username,
        'avatar': users[user_id]['avatar'],
        'message': 'Регистрация успешна!'
    })


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Заполните все поля'}), 400

    user_id = None
    for uid, u in users.items():
        if u['username'].lower() == username.lower():
            user_id = uid
            break

    if not user_id:
        return jsonify({'error': 'Пользователь не найден'}), 404

    if users[user_id]['password_hash'] != hash_password(password):
        return jsonify({'error': 'Неверный пароль'}), 401

    return jsonify({
        'user_id': user_id,
        'username': users[user_id]['username'],
        'avatar': users[user_id]['avatar'],
        'bio': users[user_id]['bio']
    })


@app.route('/api/login-by-id', methods=['POST'])
def login_by_id():
    data = request.json
    user_id = data.get('user_id', '').strip()
    password = data.get('password', '').strip()

    if not user_id or not password:
        return jsonify({'error': 'Заполните все поля'}), 400

    if user_id not in users:
        return jsonify({'error': 'Пользователь не найден'}), 404

    if users[user_id]['password_hash'] != hash_password(password):
        return jsonify({'error': 'Неверный пароль'}), 401

    return jsonify({
        'user_id': user_id,
        'username': users[user_id]['username'],
        'avatar': users[user_id]['avatar'],
        'bio': users[user_id]['bio']
    })


@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    data = request.json
    user_id = data.get('user_id', '')
    avatar = data.get('avatar', '')
    bio = data.get('bio', '')

    if user_id not in users:
        return jsonify({'error': 'Пользователь не найден'}), 404

    if avatar and avatar in AVAILABLE_AVATARS:
        users[user_id]['avatar'] = avatar
    if bio is not None and len(bio) <= 100:
        users[user_id]['bio'] = bio

    return jsonify({
        'avatar': users[user_id]['avatar'],
        'bio': users[user_id]['bio'],
        'message': 'Профиль обновлён'
    })


@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    if user_id not in users:
        return jsonify({'error': 'Не найден'}), 404
    u = users[user_id]
    return jsonify({
        'id': user_id,
        'username': u['username'],
        'avatar': u['avatar'],
        'bio': u['bio'],
        'status': 'online' if user_id in online_users else 'offline',
        'created_at': u['created_at']
    })


@app.route('/api/users', methods=['GET'])
def get_users():
    users_list = []
    for uid, u in users.items():
        users_list.append({
            'id': uid,
            'username': u['username'],
            'avatar': u['avatar'],
            'bio': u['bio'],
            'status': 'online' if uid in online_users else 'offline'
        })
    return jsonify(users_list)


@app.route('/api/avatars', methods=['GET'])
def get_avatars():
    return jsonify(AVAILABLE_AVATARS)


@socketio.on('connect')
def handle_connect():
    user_id = request.args.get('user_id')
    if user_id and user_id in users:
        online_users[user_id] = request.sid
        emit('status_update', {
            'user_id': user_id,
            'status': 'online',
            'username': users[user_id]['username']
        }, broadcast=True)


@socketio.on('disconnect')
def handle_disconnect():
    for uid, sid in list(online_users.items()):
        if sid == request.sid:
            del online_users[uid]
            if uid in users:
                emit('status_update', {
                    'user_id': uid,
                    'status': 'offline',
                    'username': users[uid]['username']
                }, broadcast=True)
            break


@socketio.on('join_chat')
def handle_join_chat(data):
    user_id = data.get('user_id')
    friend_id = data.get('friend_id')
    if user_id in users and friend_id in users:
        room = get_chat_room(user_id, friend_id)
        join_room(room)
        history = messages[room][-100:]
        emit('chat_history', history)


@socketio.on('send_message')
def handle_message(data):
    user_id = data.get('user_id')
    friend_id = data.get('friend_id')
    text = data.get('message', '').strip()
    if not text or user_id not in users or friend_id not in users:
        return

    room = get_chat_room(user_id, friend_id)
    msg = {
        'sender_id': user_id,
        'sender_name': users[user_id]['username'],
        'sender_avatar': users[user_id]['avatar'],
        'message': text,
        'timestamp': datetime.now().strftime('%H:%M')
    }
    messages[room].append(msg)
    if len(messages[room]) > 200:
        messages[room] = messages[room][-200:]

    emit('new_message', msg, room=room)

    if friend_id in online_users:
        emit('notification', {
            'from': users[user_id]['username'],
            'message': text[:60],
            'friend_id': user_id
        }, room=online_users[friend_id])


@socketio.on('add_friend')
def handle_add_friend(data):
    user_id = data.get('user_id')
    friend_id = data.get('friend_id')

    if user_id not in users or friend_id not in users:
        emit('friend_added', {'success': False, 'message': 'Пользователь не найден'})
        return
    if friend_id == user_id:
        emit('friend_added', {'success': False, 'message': 'Нельзя добавить себя'})
        return
    if friend_id in users[user_id]['friends']:
        emit('friend_added', {'success': False, 'message': 'Уже в друзьях'})
        return

    users[user_id]['friends'].append(friend_id)
    users[friend_id]['friends'].append(user_id)

    emit('friend_added', {
        'success': True,
        'message': f'{users[friend_id]["username"]} добавлен!',
        'friend': {'id': friend_id, 'username': users[friend_id]['username'], 'avatar': users[friend_id]['avatar']}
    })

    if friend_id in online_users:
        emit('friend_added', {
            'success': True,
            'message': f'{users[user_id]["username"]} добавил вас в друзья',
            'friend': {'id': user_id, 'username': users[user_id]['username'], 'avatar': users[user_id]['avatar']}
        }, room=online_users[friend_id])


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)