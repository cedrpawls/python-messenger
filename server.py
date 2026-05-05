from flask import Flask, render_template, request, jsonify, session
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

# ====== ХРАНИЛИЩЕ ======
# users = { user_id: { username, password_hash, avatar_emoji, bio, friends, created_at } }
users = {}
# messages = { room_id: [ {sender_id, sender_name, message, timestamp} ] }
messages = defaultdict(list)
# online_users = { user_id: socket_sid }
online_users = {}

# Предустановленные аватарки (эмодзи)
AVAILABLE_AVATARS = ["😎", "🦊", "🐱", "🐶", "🦁", "🐼", "🐨", "🐸", "🦄", "🐙", "👾", "🤖", "👻", "💀", "👽", "🎃", "🌟", "🔥", "💎", "🍀"]

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_id():
    return str(uuid.uuid4())[:8]

def get_chat_room(u1, u2):
    return f"chat_{'_'.join(sorted([u1, u2]))}"

# ====== API РОУТЫ ======

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

    # Проверка уникальности имени
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

    # Поиск пользователя по имени
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

# ====== SOCKET СОБЫТИЯ ======

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

# ====== ЗАПУСК ======
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)from flask import Flask, render_template, request, jsonify, session
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

# ====== ХРАНИЛИЩЕ ======
# users = { user_id: { username, password_hash, avatar_emoji, bio, friends, created_at } }
users = {}
# messages = { room_id: [ {sender_id, sender_name, message, timestamp} ] }
messages = defaultdict(list)
# online_users = { user_id: socket_sid }
online_users = {}

# Предустановленные аватарки (эмодзи)
AVAILABLE_AVATARS = ["😎", "🦊", "🐱", "🐶", "🦁", "🐼", "🐨", "🐸", "🦄", "🐙", "👾", "🤖", "👻", "💀", "👽", "🎃", "🌟", "🔥", "💎", "🍀"]

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_id():
    return str(uuid.uuid4())[:8]

def get_chat_room(u1, u2):
    return f"chat_{'_'.join(sorted([u1, u2]))}"

# ====== API РОУТЫ ======

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

    # Проверка уникальности имени
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

    # Поиск пользователя по имени
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

# ====== SOCKET СОБЫТИЯ ======

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

# ====== ЗАПУСК ======
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import uuid
import json
import os
from datetime import datetime
from collections import defaultdict

# Настройка для продакшена
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['DEBUG'] = os.environ.get('DEBUG', 'False').lower() == 'true'

# Настройка CORS для продакшена
if os.environ.get('RENDER'):
    # Разрешаем все origins на Render
    CORS(app, resources={r"/*": {"origins": "*"}})
else:
    CORS(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# Хранилище данных
users = {}
messages = defaultdict(list)
online_users = {}

class Messenger:
    @staticmethod
    def generate_id():
        return str(uuid.uuid4())[:8]
    
    @staticmethod
    def create_user(username):
        user_id = Messenger.generate_id()
        users[user_id] = {
            'username': username,
            'status': 'online',
            'friends': [],
            'created_at': datetime.now().isoformat()
        }
        return user_id
    
    @staticmethod
    def add_friend(user_id, friend_id):
        if friend_id not in users:
            return False, "Пользователь не найден"
        if friend_id == user_id:
            return False, "Нельзя добавить себя"
        if friend_id in users[user_id]['friends']:
            return False, "Уже в друзьях"
        
        users[user_id]['friends'].append(friend_id)
        users[friend_id]['friends'].append(user_id)
        
        room_id = Messenger.get_chat_room(user_id, friend_id)
        
        return True, f"Друг {users[friend_id]['username']} добавлен"
    
    @staticmethod
    def get_chat_room(user1_id, user2_id):
        sorted_ids = sorted([user1_id, user2_id])
        return f"chat_{sorted_ids[0]}_{sorted_ids[1]}"
    
    @staticmethod
    def get_user_friends(user_id):
        if user_id not in users:
            return []
        friends_list = []
        for friend_id in users[user_id]['friends']:
            if friend_id in users:  # Проверка на случай удаления
                friend = users[friend_id]
                friends_list.append({
                    'id': friend_id,
                    'username': friend['username'],
                    'status': 'online' if friend_id in online_users else 'offline'
                })
        return friends_list

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Проверка работоспособности для Render"""
    return jsonify({
        'status': 'healthy',
        'users_online': len(online_users),
        'total_users': len(users),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'error': 'Имя пользователя обязательно'}), 400
        
        if len(username) < 3:
            return jsonify({'error': 'Имя должно быть минимум 3 символа'}), 400
        
        user_id = Messenger.create_user(username)
        
        return jsonify({
            'user_id': user_id,
            'username': username,
            'message': 'Регистрация успешна! Сохраните ваш ID.',
            'server': os.environ.get('RENDER_EXTERNAL_URL', 'localhost')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['GET'])
def get_users():
    try:
        users_list = []
        for uid, user_data in users.items():
            users_list.append({
                'id': uid,
                'username': user_data['username'],
                'status': 'online' if uid in online_users else 'offline'
            })
        return jsonify(users_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    try:
        user_id = request.args.get('user_id')
        if user_id and user_id in users:
            online_users[user_id] = request.sid
            users[user_id]['status'] = 'online'
            emit('status_update', {
                'user_id': user_id,
                'status': 'online',
                'username': users[user_id]['username']
            }, broadcast=True)
            print(f"✓ Пользователь {users[user_id]['username']} подключился")
    except Exception as e:
        print(f"Ошибка подключения: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    try:
        for user_id, sid in list(online_users.items()):
            if sid == request.sid:
                del online_users[user_id]
                if user_id in users:
                    users[user_id]['status'] = 'offline'
                    emit('status_update', {
                        'user_id': user_id,
                        'status': 'offline',
                        'username': users[user_id]['username']
                    }, broadcast=True)
                    print(f"✗ Пользователь {users[user_id]['username']} отключился")
                break
    except Exception as e:
        print(f"Ошибка отключения: {e}")

@socketio.on('join_chat')
def handle_join_chat(data):
    try:
        user_id = data.get('user_id')
        friend_id = data.get('friend_id')
        
        if user_id in users and friend_id in users:
            room = Messenger.get_chat_room(user_id, friend_id)
            join_room(room)
            
            # Отправляем историю сообщений
            history = messages[room][-50:]  # Последние 50 сообщений
            emit('chat_history', history)
            
            emit('chat_info', {
                'room': room,
                'friend': {
                    'id': friend_id,
                    'username': users[friend_id]['username']
                }
            })
    except Exception as e:
        print(f"Ошибка входа в чат: {e}")

@socketio.on('send_message')
def handle_message(data):
    try:
        user_id = data.get('user_id')
        friend_id = data.get('friend_id')
        message_text = data.get('message', '').strip()
        
        if not message_text or user_id not in users or friend_id not in users:
            return
        
        room = Messenger.get_chat_room(user_id, friend_id)
        
        message_data = {
            'sender_id': user_id,
            'sender_name': users[user_id]['username'],
            'message': message_text,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        
        # Храним последние 100 сообщений
        messages[room].append(message_data)
        if len(messages[room]) > 100:
            messages[room] = messages[room][-100:]
        
        emit('new_message', message_data, room=room)
        
        # Уведомление для получателя
        if friend_id in online_users:
            emit('notification', {
                'from': users[user_id]['username'],
                'message': message_text[:50],
                'room': room,
                'friend_id': user_id
            }, room=online_users[friend_id])
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

@socketio.on('add_friend')
def handle_add_friend(data):
    try:
        user_id = data.get('user_id')
        friend_id = data.get('friend_id')
        
        if user_id in users and friend_id in users:
            success, message = Messenger.add_friend(user_id, friend_id)
            emit('friend_added', {
                'success': success,
                'message': message,
                'friend': {
                    'id': friend_id,
                    'username': users[friend_id]['username']
                } if success else None
            })
            
            if success and friend_id in online_users:
                emit('friend_added', {
                    'success': True,
                    'message': f"{users[user_id]['username']} добавил вас в друзья",
                    'friend': {
                        'id': user_id,
                        'username': users[user_id]['username']
                    }
                }, room=online_users[friend_id])
    except Exception as e:
        print(f"Ошибка добавления друга: {e}")

# Для локальной разработки
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'True').lower() == 'true'
    )
