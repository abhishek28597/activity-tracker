from flask import Flask, render_template, request, Response, jsonify
import sqlite3
from datetime import datetime, date, timedelta
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from llm_refiner import refine_text
from activity_network import build_activity_tree, tree_to_dict

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
    """Export keystrokes for a given date as a text file.
    
    Query params:
        date: Date in YYYY-MM-DD format (required)
        refine: If 'true', pass through LLM refinement pipeline (optional)
    """
    date_str = request.args.get('date')
    refine = request.args.get('refine', 'false').lower() == 'true'
    
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
    
    # Group keystrokes by app changes (like the UI display)
    output_lines = []
    current_app = None
    current_keys = []
    current_timestamp = None
    
    for ks in keystrokes:
        # When app changes, process the previous group
        if current_app is not None and ks['app_name'] != current_app:
            # Reconstruct text for previous app group
            reconstructed = reconstruct_text(current_keys)
            has_text = reconstructed.strip()
            
            # Always include app groups (even if no text, to show app switches)
            if current_timestamp:
                ts = datetime.fromisoformat(current_timestamp)
                formatted_time = ts.strftime('%-d %b %Y at %-I:%M %p')
                output_lines.append(f"{formatted_time}")
                output_lines.append(f"[{current_app}]")
                
                if has_text:
                    output_lines.append(reconstructed)
                else:
                    output_lines.append("(App switch activity)")
                output_lines.append("")  # Empty line between groups
            
            # Reset for new app
            current_keys = []
        
        # Update current app and add key
        if current_app != ks['app_name']:
            current_app = ks['app_name']
            current_timestamp = ks['timestamp']
        
        current_keys.append(ks['key_pressed'])
    
    # Process the last group
    if current_app is not None:
        reconstructed = reconstruct_text(current_keys)
        has_text = reconstructed.strip()
        
        if current_timestamp:
            ts = datetime.fromisoformat(current_timestamp)
            formatted_time = ts.strftime('%-d %b %Y at %-I:%M %p')
            output_lines.append(f"{formatted_time}")
            output_lines.append(f"[{current_app}]")
            
            if has_text:
                output_lines.append(reconstructed)
            else:
                output_lines.append("(App switch activity)")
            output_lines.append("")
    
    content = '\n'.join(output_lines)
    
    # If refinement is requested, pass through LLM
    if refine:
        content = refine_text(content)
        filename = f"{export_date.strftime('%Y-%m-%d')}_refined_key_stroke.txt"
    else:
        filename = f"{export_date.strftime('%Y-%m-%d')}_key_stroke.txt"
    
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/activity-graph')
def activity_tree():
    """Activity Graph page for generating and viewing refined keystroke text."""
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
    
    # Check if refined file exists for this date
    data_dir = 'data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    filename = f"{selected_date.strftime('%Y-%m-%d')}_refined.txt"
    filepath = os.path.join(data_dir, filename)
    file_exists = os.path.exists(filepath)
    
    # If file exists, read its content
    file_content = None
    if file_exists:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except Exception as e:
            file_content = None
    
    # Check if tree file exists for this date
    tree_filename = f"{selected_date.strftime('%Y-%m-%d')}_refined_tree.json"
    tree_filepath = os.path.join(data_dir, tree_filename)
    tree_exists = os.path.exists(tree_filepath)
    
    # If tree file exists, read its content
    tree_data = None
    if tree_exists:
        try:
            with open(tree_filepath, 'r', encoding='utf-8') as f:
                tree_data = json.load(f)
        except Exception as e:
            tree_data = None
    
    return render_template('activity_tree.html',
                         selected_date=selected_date,
                         today=today,
                         is_today=(selected_date == today),
                         file_exists=file_exists,
                         file_content=file_content,
                         filename=filename,
                         tree_exists=tree_exists,
                         tree_data=tree_data,
                         tree_filename=tree_filename)

@app.route('/api/generate-refined-text', methods=['POST'])
def generate_refined_text():
    """Generate refined text and save it to data folder."""
    data = request.get_json()
    date_str = data.get('date')
    
    if not date_str:
        return jsonify({'error': 'Missing date parameter'}), 400
    
    try:
        export_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Get keystrokes for the date
    conn = get_db_connection()
    cursor = conn.cursor()
    
    keystrokes = cursor.execute('''
        SELECT timestamp, key_pressed, app_name
        FROM keystroke_log
        WHERE DATE(timestamp) = ?
        ORDER BY timestamp ASC
    ''', (export_date.isoformat(),)).fetchall()
    
    conn.close()
    
    if not keystrokes:
        return jsonify({'error': f'No keystrokes recorded for {export_date.strftime("%Y-%m-%d")}'}), 404
    
    # Group keystrokes by app changes (like the UI display)
    output_lines = []
    current_app = None
    current_keys = []
    current_timestamp = None
    
    for ks in keystrokes:
        # When app changes, process the previous group
        if current_app is not None and ks['app_name'] != current_app:
            # Reconstruct text for previous app group
            reconstructed = reconstruct_text(current_keys)
            has_text = reconstructed.strip()
            
            # Always include app groups (even if no text, to show app switches)
            if current_timestamp:
                ts = datetime.fromisoformat(current_timestamp)
                formatted_time = ts.strftime('%-d %b %Y at %-I:%M %p')
                output_lines.append(f"{formatted_time}")
                output_lines.append(f"[{current_app}]")
                
                if has_text:
                    output_lines.append(reconstructed)
                else:
                    output_lines.append("(App switch activity)")
                output_lines.append("")  # Empty line between groups
            
            # Reset for new app
            current_keys = []
        
        # Update current app and add key
        if current_app != ks['app_name']:
            current_app = ks['app_name']
            current_timestamp = ks['timestamp']
        
        current_keys.append(ks['key_pressed'])
    
    # Process the last group
    if current_app is not None:
        reconstructed = reconstruct_text(current_keys)
        has_text = reconstructed.strip()
        
        if current_timestamp:
            ts = datetime.fromisoformat(current_timestamp)
            formatted_time = ts.strftime('%-d %b %Y at %-I:%M %p')
            output_lines.append(f"{formatted_time}")
            output_lines.append(f"[{current_app}]")
            
            if has_text:
                output_lines.append(reconstructed)
            else:
                output_lines.append("(App switch activity)")
            output_lines.append("")
    
    content = '\n'.join(output_lines)
    
    # Refine the content
    try:
        refined_content = refine_text(content)
    except Exception as e:
        return jsonify({'error': f'Refinement failed: {str(e)}'}), 500
    
    # Save to data folder
    data_dir = 'data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    filename = f"{export_date.strftime('%Y-%m-%d')}_refined.txt"
    filepath = os.path.join(data_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(refined_content)
    except Exception as e:
        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500
    
    return jsonify({
        'success': True,
        'content': refined_content,
        'filename': filename
    })

@app.route('/api/generate-activity-graph', methods=['POST'])
def generate_activity_tree():
    """Generate activity graph from refined text and save to data folder."""
    data = request.get_json()
    date_str = data.get('date')
    
    if not date_str:
        return jsonify({'error': 'Missing date parameter'}), 400
    
    try:
        export_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Check if refined text file exists
    data_dir = 'data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    refined_filename = f"{export_date.strftime('%Y-%m-%d')}_refined.txt"
    refined_filepath = os.path.join(data_dir, refined_filename)
    
    if not os.path.exists(refined_filepath):
        return jsonify({'error': f'Refined text file not found for {date_str}. Please generate refined text first.'}), 404
    
    try:
        # Build the activity graph
        nodes = build_activity_tree(refined_filepath)
        
        if not nodes:
            return jsonify({'error': 'Failed to build activity graph. No activities found.'}), 500
        
        # Convert to JSON-serializable dict (with full content for API)
        tree_data = tree_to_dict(nodes, truncate_content=False)
        
        # Save to data folder
        tree_filename = f"{export_date.strftime('%Y-%m-%d')}_refined_tree.json"
        tree_filepath = os.path.join(data_dir, tree_filename)
        
        with open(tree_filepath, 'w', encoding='utf-8') as f:
            json.dump(tree_data, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'tree': tree_data,
            'filename': tree_filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to generate activity graph: {str(e)}'}), 500

@app.route('/api/weekly-activity')
def weekly_activity():
    """Get hourly keystroke data for the last 7 days."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Calculate date range (last 7 days including today)
    today = date.today()
    start_date = today - timedelta(days=6)  # 7 days total (today + 6 previous days)
    
    # Get hourly activity for last 7 days
    weekly_data = cursor.execute('''
        SELECT DATE(timestamp) as date, hour, SUM(keystrokes) as total_keystrokes
        FROM activity_log
        WHERE DATE(timestamp) >= ? AND DATE(timestamp) <= ?
        GROUP BY DATE(timestamp), hour
        ORDER BY date DESC, hour ASC
    ''', (start_date.isoformat(), today.isoformat())).fetchall()
    
    conn.close()
    
    # Convert to list of dicts
    data = []
    max_keystrokes = 0
    
    for row in weekly_data:
        keystrokes = row['total_keystrokes'] or 0
        data.append({
            'date': row['date'],
            'hour': row['hour'],
            'keystrokes': keystrokes
        })
        if keystrokes > max_keystrokes:
            max_keystrokes = keystrokes
    
    return jsonify({
        'data': data,
        'max_keystrokes': max_keystrokes
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)