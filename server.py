from flask import Flask, render_template, request, jsonify, send_from_directory
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPLOAD_FOLDER = 'uploads'
AVATARS_FOLDER = os.path.join(UPLOAD_FOLDER, 'avatars')
FILES_FOLDER = os.path.join(UPLOAD_FOLDER, 'files')

os.makedirs(AVATARS_FOLDER, exist_ok=True)
os.makedirs(FILES_FOLDER, exist_ok=True)

CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=False)

users = {}
messages = defaultdict(list)
online_users = {}

AVAILABLE_AVATARS = ["😎", "🦊", "🐱", "🐶", "🦁", "🐼", "🐨", "🐸", "🦄", "🐙", "👾", "🤖", "👻", "💀", "👽", "🎃", "🌟", "🔥", "💎", "🍀"]
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

SPECIAL_USER_ID = "cedrpawlsofficial"
SPECIAL_USERNAME = "CedrPawls"
SPECIAL_AVATAR = "⭐"
SPECIAL_SECRET_KEY = "CedrPawls2026!"


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_id():
    return str(uuid.uuid4())[:8]


def get_chat_room(u1, u2):
    return f"chat_{'_'.join(sorted([u1, u2]))}"


def get_avatar_url(user_id):
    for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
        avatar_path = os.path.join(AVATARS_FOLDER, f"{user_id}.{ext}")
        if os.path.exists(avatar_path):
            return f"/uploads/avatars/{user_id}.{ext}"
    return None


def get_display_name(user):
    if user.get('is_owner', False):
        return f"⭐ {user['username']}"
    return user['username']


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    avatar = data.get('avatar', '😎')
    special_id = data.get('special_id', '').strip()
    secret_key = data.get('secret_key', '').strip()

    if not username or len(username) < 3:
        return jsonify({'error': 'Имя должно быть минимум 3 символа'}), 400
    if not password or len(password) < 4:
        return jsonify({'error': 'Пароль должен быть минимум 4 символа'}), 400

    if special_id == SPECIAL_USER_ID:
        if secret_key != SPECIAL_SECRET_KEY:
            return jsonify({'error': 'Неверный секретный ключ владельца'}), 403
        if SPECIAL_USER_ID in users:
            return jsonify({'error': 'Аккаунт владельца уже создан'}), 400
        user_id = SPECIAL_USER_ID
        username = SPECIAL_USERNAME
        avatar = SPECIAL_AVATAR
    else:
        for u in users.values():
            if u['username'].lower() == username.lower():
                return jsonify({'error': 'Имя уже занято'}), 400
        user_id = generate_id()

    users[user_id] = {
        'username': username,
        'password_hash': hash_password(password),
        'avatar': avatar,
        'custom_avatar': False,
        'bio': '',
        'friends': [],
        'is_owner': (user_id == SPECIAL_USER_ID),
        'created_at': datetime.now().isoformat()
    }

    return jsonify({
        'user_id': user_id,
        'username': username,
        'avatar': avatar,
        'is_owner': (user_id == SPECIAL_USER_ID),
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
        'custom_avatar_url': get_avatar_url(user_id),
        'bio': users[user_id]['bio'],
        'is_owner': users[user_id].get('is_owner', False)
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
        'custom_avatar_url': get_avatar_url(user_id),
        'bio': users[user_id]['bio'],
        'is_owner': users[user_id].get('is_owner', False)
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
        'custom_avatar_url': get_avatar_url(user_id),
        'bio': users[user_id]['bio'],
        'is_owner': users[user_id].get('is_owner', False),
        'message': 'Профиль обновлён'
    })


@app.route('/api/upload-avatar', methods=['POST'])
def upload_avatar():
    user_id = request.form.get('user_id', '')
    if user_id not in users:
        return jsonify({'error': 'Пользователь не найден'}), 404

    if 'avatar' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400

    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Разрешены только PNG, JPG, GIF, WEBP'}), 400

    for ext in ALLOWED_EXTENSIONS:
        old_path = os.path.join(AVATARS_FOLDER, f"{user_id}.{ext}")
        if os.path.exists(old_path):
            os.remove(old_path)

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{user_id}.{ext}"
    filepath = os.path.join(AVATARS_FOLDER, filename)
    file.save(filepath)

    users[user_id]['custom_avatar'] = True
    avatar_url = f"/uploads/avatars/{filename}"

    return jsonify({
        'avatar_url': avatar_url,
        'message': 'Аватар обновлён!'
    })


@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    user_id = request.form.get('user_id', '')
    friend_id = request.form.get('friend_id', '')

    if user_id not in users or friend_id not in users:
        return jsonify({'error': 'Пользователь не найден'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    from werkzeug.utils import secure_filename
    original_filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())[:8]
    ext = original_filename.rsplit('.', 1)[1] if '.' in original_filename else ''
    saved_filename = f"{file_id}.{ext}" if ext else file_id
    filepath = os.path.join(FILES_FOLDER, saved_filename)
    file.save(filepath)

    file_url = f"/uploads/files/{saved_filename}"
    file_size = os.path.getsize(filepath)

    if file_size < 1024:
        size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        size_str = f"{file_size / 1024:.1f} KB"
    else:
        size_str = f"{file_size / (1024 * 1024):.1f} MB"

    room = get_chat_room(user_id, friend_id)
    msg = {
        'sender_id': user_id,
        'sender_name': get_display_name(users[user_id]),
        'type': 'file',
        'file_url': file_url,
        'file_name': original_filename,
        'file_size': size_str,
        'timestamp': datetime.now().strftime('%H:%M')
    }
    messages[room].append(msg)
    socketio.emit('new_message', msg, room=room)

    if friend_id in online_users:
        socketio.emit('notification', {
            'from': get_display_name(users[user_id]),
            'message': f'📎 Файл: {original_filename}',
            'friend_id': user_id
        }, room=online_users[friend_id])

    return jsonify({'file_url': file_url, 'file_name': original_filename, 'file_size': size_str})


@app.route('/api/users', methods=['GET'])
def get_users():
    users_list = []
    for uid, u in users.items():
        is_owner = u.get('is_owner', False)
        users_list.append({
            'id': uid,
            'display_id': '****' if is_owner else uid,
            'username': u['username'],
            'display_name': get_display_name(u),
            'avatar': u['avatar'],
            'custom_avatar_url': get_avatar_url(uid),
            'bio': u['bio'],
            'status': 'online' if uid in online_users else 'offline',
            'is_owner': is_owner
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
            'username': get_display_name(users[user_id])
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
                    'username': get_display_name(users[uid])
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
        'sender_name': get_display_name(users[user_id]),
        'type': 'text',
        'message': text,
        'timestamp': datetime.now().strftime('%H:%M')
    }
    messages[room].append(msg)
    if len(messages[room]) > 200:
        messages[room] = messages[room][-200:]

    emit('new_message', msg, room=room)

    if friend_id in online_users:
        emit('notification', {
            'from': get_display_name(users[user_id]),
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
        'message': f'{get_display_name(users[friend_id])} добавлен!',
        'friend': {'id': friend_id, 'username': users[friend_id]['username'], 'display_name': get_display_name(users[friend_id])}
    })

    if friend_id in online_users:
        emit('friend_added', {
            'success': True,
            'message': f'{get_display_name(users[user_id])} добавил вас в друзья',
            'friend': {'id': user_id, 'username': users[user_id]['username'], 'display_name': get_display_name(users[user_id])}
        }, room=online_users[friend_id])


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)