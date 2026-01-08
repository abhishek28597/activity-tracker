from flask import Flask, render_template, request, Response
import sqlite3
from datetime import datetime, date, timedelta
import json

app = Flask(__name__)

# Keys to ignore during text reconstruction
IGNORE_KEYS = {
    'shift', 'shift_r', 'ctrl', 'ctrl_r', 'alt', 'alt_r', 'alt_gr',
    'cmd', 'cmd_r', 'caps_lock', 'up', 'down', 'left', 'right',
    'home', 'end', 'page_up', 'page_down', 'delete', 'escape',
    'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
    'tab', 'print_screen', 'scroll_lock', 'pause', 'insert', 'num_lock',
    'menu'
}

def reconstruct_text(keystrokes):
    """Reconstruct readable text from a list of keystrokes."""
    result = []
    for key in keystrokes:
        key_lower = key.lower()
        
        # Skip ignored keys
        if key_lower in IGNORE_KEYS:
            continue
        
        # Handle special keys
        if key_lower == 'backspace':
            if result:
                result.pop()
        elif key_lower == 'space':
            result.append(' ')
        elif key_lower in ('enter', 'return'):
            result.append('\n')
        elif len(key) == 1:
            # Regular character
            result.append(key)
    
    return ''.join(result)

def get_db_connection():
    conn = sqlite3.connect('activity.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get date from query parameter, default to today
    date_str = request.args.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    today = date.today()
    
    # Get hourly activity for selected date
    hourly_data = cursor.execute('''
        SELECT hour, SUM(keystrokes) as total_keystrokes, SUM(clicks) as total_clicks
        FROM activity_log
        WHERE DATE(timestamp) = ?
        GROUP BY hour
        ORDER BY hour
    ''', (selected_date.isoformat(),)).fetchall()
    
    # Get app usage for selected date
    app_usage = cursor.execute('''
        SELECT app_name, 
               SUM(keystrokes) as total_keystrokes,
               SUM(clicks) as total_clicks,
               COUNT(*) as minutes_active
        FROM activity_log
        WHERE DATE(timestamp) = ?
        GROUP BY app_name
        ORDER BY minutes_active DESC
        LIMIT 10
    ''', (selected_date.isoformat(),)).fetchall()
    
    # Get productivity metrics
    total_activity = cursor.execute('''
        SELECT 
            SUM(keystrokes) as total_keystrokes,
            SUM(clicks) as total_clicks,
            COUNT(DISTINCT hour) as active_hours,
            MIN(hour) as first_active_hour,
            MAX(hour) as last_active_hour
        FROM activity_log
        WHERE DATE(timestamp) = ?
    ''', (selected_date.isoformat(),)).fetchone()
    
    # Find most productive hour
    most_productive = cursor.execute('''
        SELECT hour, SUM(keystrokes) + SUM(clicks) as total_activity
        FROM activity_log
        WHERE DATE(timestamp) = ?
        GROUP BY hour
        ORDER BY total_activity DESC
        LIMIT 1
    ''', (selected_date.isoformat(),)).fetchone()
    
    # Get recent keystrokes (last 500) - fetch newest first, then reverse for display
    recent_keystrokes = cursor.execute('''
        SELECT timestamp, key_pressed, app_name
        FROM keystroke_log
        WHERE DATE(timestamp) = ?
        ORDER BY timestamp DESC
        LIMIT 500
    ''', (selected_date.isoformat(),)).fetchall()
    # Reverse to display in chronological order (oldest to newest for stream readability)
    recent_keystrokes = list(reversed(recent_keystrokes))
    
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
                         hourly_keystrokes_list=keystrokes_by_hour,
                         hourly_clicks=json.dumps(clicks_by_hour),
                         hours=json.dumps(hours),
                         app_usage=app_usage,
                         total_activity=total_activity,
                         most_productive=most_productive,
                         recent_keystrokes=recent_keystrokes,
                         selected_date=selected_date,
                         today=today,
                         is_today=(selected_date == today))

@app.route('/api/export-keystrokes')
def export_keystrokes():
    """Export keystrokes for a given date as a text file."""
    date_str = request.args.get('date')
    
    if not date_str:
        return Response("Missing date parameter", status=400)
    
    try:
        export_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response("Invalid date format. Use YYYY-MM-DD", status=400)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all keystrokes for the date, ordered by timestamp
    keystrokes = cursor.execute('''
        SELECT timestamp, key_pressed, app_name
        FROM keystroke_log
        WHERE DATE(timestamp) = ?
        ORDER BY timestamp ASC
    ''', (export_date.isoformat(),)).fetchall()
    
    conn.close()
    
    if not keystrokes:
        # Return empty file with message
        content = f"No keystrokes recorded for {export_date.strftime('%d %b %Y')}\n"
        filename = f"{export_date.strftime('%Y-%m-%d')}_key_stroke.txt"
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    
    # Group keystrokes into 30-minute intervals
    intervals = {}
    for ks in keystrokes:
        ts = datetime.fromisoformat(ks['timestamp'])
        # Round down to nearest 30 minutes
        minute_slot = (ts.minute // 30) * 30
        interval_start = ts.replace(minute=minute_slot, second=0, microsecond=0)
        interval_key = interval_start.strftime('%Y-%m-%d %H:%M')
        
        if interval_key not in intervals:
            intervals[interval_key] = []
        intervals[interval_key].append(ks['key_pressed'])
    
    # Build the output text
    output_lines = []
    for interval_key in sorted(intervals.keys()):
        keys = intervals[interval_key]
        reconstructed = reconstruct_text(keys)
        
        # Skip if reconstructed text is empty or just whitespace
        if not reconstructed.strip():
            continue
        
        # Format the timestamp nicely: "5 Jan 2026 at 1:00 PM"
        interval_dt = datetime.strptime(interval_key, '%Y-%m-%d %H:%M')
        formatted_time = interval_dt.strftime('%-d %b %Y at %-I:%M %p')
        
        output_lines.append(f"{formatted_time}")
        output_lines.append(reconstructed)
        output_lines.append("")  # Empty line between intervals
    
    content = '\n'.join(output_lines)
    filename = f"{export_date.strftime('%Y-%m-%d')}_key_stroke.txt"
    
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)