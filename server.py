from flask import Flask, render_template, request, jsonify
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