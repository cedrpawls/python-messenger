import socketio
import requests
import threading
import time
import os
import json
from datetime import datetime

class MessengerClient:
    def __init__(self, server_url='http://localhost:5000'):
        self.server_url = server_url
        self.sio = socketio.Client()
        self.user_id = None
        self.username = None
        self.current_chat = None
        self.current_friend_id = None
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков событий"""
        
        @self.sio.on('connect')
        def on_connect():
            print("\n✓ Подключен к серверу")
        
        @self.sio.on('disconnect')
        def on_disconnect():
            print("\n✗ Отключен от сервера")
        
        @self.sio.on('chat_history')
        def on_chat_history(history):
            print("\n" + "="*50)
            print("История сообщений:")
            print("-"*50)
            for msg in history:
                self.print_message(msg)
            print("="*50)
        
        @self.sio.on('new_message')
        def on_new_message(data):
            if self.current_chat:
                self.print_message(data)
        
        @self.sio.on('notification')
        def on_notification(data):
            print(f"\n🔔 Новое сообщение от {data['from']}: {data['message']}")
        
        @self.sio.on('friend_added')
        def on_friend_added(data):
            if data['success']:
                print(f"\n✓ {data['message']}")
            else:
                print(f"\n✗ {data['message']}")
        
        @self.sio.on('status_update')
        def on_status_update(data):
            username = self.get_username_by_id(data['user_id'])
            status = "онлайн" if data['status'] == 'online' else "офлайн"
            print(f"\n📱 {username} теперь {status}")
    
    def get_username_by_id(self, user_id):
        """Получение имени пользователя по ID"""
        try:
            response = requests.get(f"{self.server_url}/api/users")
            if response.status_code == 200:
                users = response.json()
                for user in users:
                    if user['id'] == user_id:
                        return user['username']
        except:
            pass
        return user_id
    
    def print_message(self, msg):
        """Вывод сообщения"""
        is_me = msg['sender_id'] == self.user_id
        prefix = "Вы" if is_me else msg['sender_name']
        print(f"[{msg['timestamp']}] {prefix}: {msg['message']}")
    
    def connect(self, user_id=None):
        """Подключение к серверу"""
        if user_id:
            self.user_id = user_id
        self.sio.connect(f"{self.server_url}?user_id={self.user_id}")
    
    def register(self, username):
        """Регистрация нового пользователя"""
        try:
            response = requests.post(
                f"{self.server_url}/api/register",
                json={'username': username}
            )
            if response.status_code == 200:
                data = response.json()
                self.user_id = data['user_id']
                self.username = data['username']
                return data
            else:
                print(f"Ошибка: {response.json().get('error')}")
                return None
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return None
    
    def add_friend(self, friend_id):
        """Добавление друга"""
        self.sio.emit('add_friend', {
            'user_id': self.user_id,
            'friend_id': friend_id
        })
    
    def open_chat(self, friend_id):
        """Открыть чат с другом"""
        self.current_friend_id = friend_id
        self.sio.emit('join_chat', {
            'user_id': self.user_id,
            'friend_id': friend_id
        })
    
    def send_message(self, message):
        """Отправить сообщение"""
        if self.current_friend_id:
            self.sio.emit('send_message', {
                'user_id': self.user_id,
                'friend_id': self.current_friend_id,
                'message': message
            })
    
    def show_users(self):
        """Показать всех пользователей"""
        try:
            response = requests.get(f"{self.server_url}/api/users")
            if response.status_code == 200:
                users = response.json()
                print("\n" + "="*50)
                print("Список пользователей:")
                print("-"*50)
                for user in users:
                    status_icon = "🟢" if user['status'] == 'online' else "⚫"
                    is_me = " (Вы)" if user['id'] == self.user_id else ""
                    print(f"{status_icon} {user['username']} - ID: {user['id']}{is_me}")
                print("="*50)
        except:
            print("Не удалось загрузить список пользователей")
    
    def run(self):
        """Запуск клиента"""
        print("\n" + "="*50)
        print("ДОБРО ПОЖАЛОВАТЬ В МЕССЕНДЖЕР")
        print("="*50)
        
        while True:
            if not self.user_id:
                print("\n1. Войти по существующему ID")
                print("2. Зарегистрироваться")
                choice = input("Выберите действие (1/2): ")
                
                if choice == '1':
                    user_id = input("Введите ваш ID: ").strip()
                    if user_id:
                        try:
                            self.connect(user_id)
                            print(f"✓ Вход выполнен")
                        except:
                            print("✗ Неверный ID или сервер недоступен")
                
                elif choice == '2':
                    username = input("Введите имя пользователя: ").strip()
                    if username:
                        result = self.register(username)
                        if result:
                            print(f"\n✓ Регистрация успешна!")
                            print(f"Ваш ID: {result['user_id']}")
                            print(f"Сохраните его для входа!")
                            self.connect()
            
            else:
                print("\n" + "-"*50)
                print(f"Вы вошли как: {self.username}")
                print(f"Ваш ID: {self.user_id}")
                print("-"*50)
                print("1. Показать пользователей")
                print("2. Добавить друга")
                print("3. Открыть чат")
                print("4. Отправить сообщение")
                print("5. Выйти")
                
                choice = input("\nВыберите действие: ")
                
                if choice == '1':
                    self.show_users()
                
                elif choice == '2':
                    friend_id = input("Введите ID друга: ").strip()
                    if friend_id:
                        self.add_friend(friend_id)
                
                elif choice == '3':
                    friend_id = input("Введите ID друга для чата: ").strip()
                    if friend_id:
                        self.open_chat(friend_id)
                        print(f"\n✓ Чат открыт. Введите 'quit' для выхода из чата.")
                        
                        # Режим чата
                        while True:
                            message = input()
                            if message.lower() == 'quit':
                                self.current_chat = False
                                self.current_friend_id = None
                                break
                            self.send_message(message)
                
                elif choice == '4':
                    if self.current_friend_id:
                        message = input("Сообщение: ")
                        self.send_message(message)
                    else:
                        print("Сначала откройте чат (пункт 3)")
                
                elif choice == '5':
                    self.sio.disconnect()
                    break

if __name__ == '__main__':
    # Используйте ваш URL сервера здесь
    SERVER_URL = 'http://localhost:5000'  # Замените на ваш URL
    
    client = MessengerClient(SERVER_URL)
    client.run()