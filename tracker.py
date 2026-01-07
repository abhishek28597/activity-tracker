import time
import sqlite3
from datetime import datetime
from pynput import keyboard, mouse
import threading
import subprocess
import re

class ActivityTracker:
    def __init__(self):
        self.keystroke_count = 0
        self.mouse_clicks = 0
        self.current_app = ""
        self.last_save = time.time()
        self.keystroke_buffer = []  # Buffer to store individual keystrokes
        self.init_database()
        self.start_tracking()
    
    def init_database(self):
        self.conn = sqlite3.connect('activity.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                timestamp DATETIME,
                hour INTEGER,
                app_name TEXT,
                keystrokes INTEGER,
                clicks INTEGER
            )
        ''')
        # New table to store individual keystrokes
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS keystroke_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                key_pressed TEXT,
                app_name TEXT
            )
        ''')
        self.conn.commit()
    
    def get_active_app(self):
        try:
            # Get active window using AppleScript
            script = '''
            tell application "System Events"
                set frontApp to name of first application process whose frontmost is true
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "Unknown"
    
    def on_key_press(self, key):
        self.keystroke_count += 1
        
        # Convert key to readable string
        try:
            key_str = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
        except AttributeError:
            key_str = str(key).replace('Key.', '')
        
        # Add to buffer with timestamp and current app
        current_app = self.get_active_app()
        self.keystroke_buffer.append({
            'timestamp': datetime.now(),
            'key': key_str,
            'app': current_app
        })
    
    def on_click(self, x, y, button, pressed):
        if pressed:
            self.mouse_clicks += 1
    
    def save_activity(self):
        while True:
            time.sleep(60)  # Save every minute
            
            current_hour = datetime.now().hour
            
            if self.keystroke_count > 0 or self.mouse_clicks > 0:
                # Aggregate keystrokes by app from the buffer
                app_keystrokes = {}
                for keystroke in self.keystroke_buffer:
                    app = keystroke['app']
                    app_keystrokes[app] = app_keystrokes.get(app, 0) + 1
                
                # Save individual keystrokes from buffer
                for keystroke in self.keystroke_buffer:
                    self.cursor.execute('''
                        INSERT INTO keystroke_log (timestamp, key_pressed, app_name)
                        VALUES (?, ?, ?)
                    ''', (keystroke['timestamp'], keystroke['key'], keystroke['app']))
                
                # Distribute clicks to the app with most keystrokes (best approximation)
                # or to current app if no keystrokes
                if app_keystrokes:
                    main_app = max(app_keystrokes, key=app_keystrokes.get)
                else:
                    main_app = self.get_active_app()
                
                # Save activity_log entries for each app
                for app, key_count in app_keystrokes.items():
                    # Give clicks to the main app only
                    clicks = self.mouse_clicks if app == main_app else 0
                    self.cursor.execute('''
                        INSERT INTO activity_log 
                        (timestamp, hour, app_name, keystrokes, clicks)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (datetime.now(), current_hour, app, key_count, clicks))
                
                # If there were clicks but no keystrokes, still log the clicks
                if not app_keystrokes and self.mouse_clicks > 0:
                    current_app = self.get_active_app()
                    self.cursor.execute('''
                        INSERT INTO activity_log 
                        (timestamp, hour, app_name, keystrokes, clicks)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (datetime.now(), current_hour, current_app, 0, self.mouse_clicks))
                
                self.conn.commit()
                
                print(f"Logged: {app_keystrokes} keys, {self.mouse_clicks} clicks")
                
                # Reset counters and buffer
                self.keystroke_count = 0
                self.mouse_clicks = 0
                self.keystroke_buffer = []
    
    def start_tracking(self):
        # Start keyboard listener
        keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        keyboard_listener.start()
        
        # Start mouse listener
        mouse_listener = mouse.Listener(on_click=self.on_click)
        mouse_listener.start()
        
        # Start save thread
        save_thread = threading.Thread(target=self.save_activity)
        save_thread.daemon = True
        save_thread.start()
        
        print("Activity tracking started...")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping tracker...")
            keyboard_listener.stop()
            mouse_listener.stop()

if __name__ == "__main__":
    tracker = ActivityTracker()