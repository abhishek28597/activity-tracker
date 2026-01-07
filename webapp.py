from flask import Flask, render_template
import sqlite3
from datetime import datetime, date
import json

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('activity.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = date.today()
    
    # Get hourly activity for today
    hourly_data = cursor.execute('''
        SELECT hour, SUM(keystrokes) as total_keystrokes, SUM(clicks) as total_clicks
        FROM activity_log
        WHERE DATE(timestamp) = DATE('now', 'localtime')
        GROUP BY hour
        ORDER BY hour
    ''').fetchall()
    
    # Get app usage for today
    app_usage = cursor.execute('''
        SELECT app_name, 
               SUM(keystrokes) as total_keystrokes,
               SUM(clicks) as total_clicks,
               COUNT(*) as minutes_active
        FROM activity_log
        WHERE DATE(timestamp) = DATE('now', 'localtime')
        GROUP BY app_name
        ORDER BY minutes_active DESC
        LIMIT 10
    ''').fetchall()
    
    # Get productivity metrics
    total_activity = cursor.execute('''
        SELECT 
            SUM(keystrokes) as total_keystrokes,
            SUM(clicks) as total_clicks,
            COUNT(DISTINCT hour) as active_hours,
            MIN(hour) as first_active_hour,
            MAX(hour) as last_active_hour
        FROM activity_log
        WHERE DATE(timestamp) = DATE('now', 'localtime')
    ''').fetchone()
    
    # Find most productive hour
    most_productive = cursor.execute('''
        SELECT hour, SUM(keystrokes) + SUM(clicks) as total_activity
        FROM activity_log
        WHERE DATE(timestamp) = DATE('now', 'localtime')
        GROUP BY hour
        ORDER BY total_activity DESC
        LIMIT 1
    ''').fetchone()
    
    # Get recent keystrokes (last 200)
    recent_keystrokes = cursor.execute('''
        SELECT timestamp, key_pressed, app_name
        FROM keystroke_log
        WHERE DATE(timestamp) = DATE('now', 'localtime')
        ORDER BY timestamp ASC
        LIMIT 200
    ''').fetchall()
    
    conn.close()
    
    # Prepare data for charts
    hours = list(range(24))
    keystrokes_by_hour = [0] * 24
    clicks_by_hour = [0] * 24
    
    for row in hourly_data:
        keystrokes_by_hour[row['hour']] = row['total_keystrokes']
        clicks_by_hour[row['hour']] = row['total_clicks']
    
    return render_template('dashboard.html',
                         hourly_keystrokes=json.dumps(keystrokes_by_hour),
                         hourly_clicks=json.dumps(clicks_by_hour),
                         hours=json.dumps(hours),
                         app_usage=app_usage,
                         total_activity=total_activity,
                         most_productive=most_productive,
                         recent_keystrokes=recent_keystrokes,
                         today=today)

if __name__ == '__main__':
    app.run(debug=True, port=5000)