from flask import Flask, render_template, request, Response, jsonify
from datetime import datetime, date, timedelta
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from llm_refiner import refine_text
from activity_network import build_activity_tree, tree_to_dict
from config import (
    DATABASE_PATH,
    KEYSTROKE_LIMIT_DASHBOARD,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    DB_TABLE_ACTIVITY_LOG,
    DB_TABLE_KEYSTROKE_LOG
)
from db_utils import get_db_connection
from date_utils import parse_date_param, format_date_filename
from keystroke_utils import group_keystrokes_by_app, format_keystroke_groups
from file_utils import (
    ensure_data_directory,
    get_refined_text_path,
    get_activity_tree_path,
    get_keystroke_export_filename,
    read_text_file,
    write_text_file,
    read_json_file,
    write_json_file
)

app = Flask(__name__)

@app.route('/')
def dashboard():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get date from query parameter, default to today
        selected_date = parse_date_param(request.args.get('date'))
        today = date.today()
    
        # Get hourly activity for selected date
        hourly_data = cursor.execute(f'''
            SELECT hour, SUM(keystrokes) as total_keystrokes, SUM(clicks) as total_clicks
            FROM {DB_TABLE_ACTIVITY_LOG}
            WHERE DATE(timestamp) = ?
            GROUP BY hour
            ORDER BY hour
        ''', (selected_date.isoformat(),)).fetchall()

        # Get app usage for selected date
        app_usage = cursor.execute(f'''
            SELECT app_name,
                   SUM(keystrokes) as total_keystrokes,
                   SUM(clicks) as total_clicks,
                   COUNT(*) as minutes_active
            FROM {DB_TABLE_ACTIVITY_LOG}
            WHERE DATE(timestamp) = ?
            GROUP BY app_name
            ORDER BY minutes_active DESC
            LIMIT 10
        ''', (selected_date.isoformat(),)).fetchall()

        # Get productivity metrics
        total_activity = cursor.execute(f'''
            SELECT
                SUM(keystrokes) as total_keystrokes,
                SUM(clicks) as total_clicks,
                COUNT(DISTINCT hour) as active_hours,
                MIN(hour) as first_active_hour,
                MAX(hour) as last_active_hour
            FROM {DB_TABLE_ACTIVITY_LOG}
            WHERE DATE(timestamp) = ?
        ''', (selected_date.isoformat(),)).fetchone()

        # Find most productive hour
        most_productive = cursor.execute(f'''
            SELECT hour, SUM(keystrokes) + SUM(clicks) as total_activity
            FROM {DB_TABLE_ACTIVITY_LOG}
            WHERE DATE(timestamp) = ?
            GROUP BY hour
            ORDER BY total_activity DESC
            LIMIT 1
        ''', (selected_date.isoformat(),)).fetchone()

        # Get recent keystrokes (limit from config) - fetch newest first, then reverse for display
        recent_keystrokes = cursor.execute(f'''
            SELECT timestamp, key_pressed, app_name
            FROM {DB_TABLE_KEYSTROKE_LOG}
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (selected_date.isoformat(), KEYSTROKE_LIMIT_DASHBOARD)).fetchall()
        # Reverse to display in chronological order (oldest to newest for stream readability)
        recent_keystrokes = list(reversed(recent_keystrokes))
    
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

    export_date = parse_date_param(date_str, default_to_today=False)
    if export_date is None:
        return Response("Invalid date format. Use YYYY-MM-DD", status=400)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all keystrokes for the date, ordered by timestamp
        keystrokes = cursor.execute(f'''
            SELECT timestamp, key_pressed, app_name
            FROM {DB_TABLE_KEYSTROKE_LOG}
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp ASC
        ''', (export_date.isoformat(),)).fetchall()

    if not keystrokes:
        # Return empty file with message
        content = f"No keystrokes recorded for {export_date.strftime('%d %b %Y')}\n"
        filename = get_keystroke_export_filename(export_date, refined=False)
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    # Group keystrokes by app and format
    groups = group_keystrokes_by_app(keystrokes)
    content = format_keystroke_groups(groups)

    # If refinement is requested, pass through LLM
    if refine:
        content = refine_text(content)

    filename = get_keystroke_export_filename(export_date, refined=refine)

    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/activity-graph')
def activity_tree():
    """Activity Graph page for generating and viewing refined keystroke text."""
    # Get date from query parameter, default to today
    selected_date = parse_date_param(request.args.get('date'))
    today = date.today()

    # Check if refined file exists for this date
    refined_path = get_refined_text_path(selected_date)
    file_content = read_text_file(refined_path)
    file_exists = file_content is not None
    filename = refined_path.name

    # Check if tree file exists for this date
    tree_path = get_activity_tree_path(selected_date)
    tree_data = read_json_file(tree_path)
    tree_exists = tree_data is not None
    tree_filename = tree_path.name

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

    export_date = parse_date_param(date_str, default_to_today=False)
    if export_date is None:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Get keystrokes for the date
    with get_db_connection() as conn:
        cursor = conn.cursor()

        keystrokes = cursor.execute(f'''
            SELECT timestamp, key_pressed, app_name
            FROM {DB_TABLE_KEYSTROKE_LOG}
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp ASC
        ''', (export_date.isoformat(),)).fetchall()

    if not keystrokes:
        return jsonify({'error': f'No keystrokes recorded for {export_date.strftime("%Y-%m-%d")}'}), 404

    # Group keystrokes by app and format
    groups = group_keystrokes_by_app(keystrokes)
    content = format_keystroke_groups(groups)

    # Refine the content
    try:
        refined_content = refine_text(content)
    except Exception as e:
        return jsonify({'error': f'Refinement failed: {str(e)}'}), 500

    # Save to data folder
    refined_path = get_refined_text_path(export_date)
    if not write_text_file(refined_path, refined_content):
        return jsonify({'error': 'Failed to save file'}), 500

    return jsonify({
        'success': True,
        'content': refined_content,
        'filename': refined_path.name
    })

@app.route('/api/generate-activity-graph', methods=['POST'])
def generate_activity_tree():
    """Generate activity graph from refined text and save to data folder."""
    data = request.get_json()
    date_str = data.get('date')

    if not date_str:
        return jsonify({'error': 'Missing date parameter'}), 400

    export_date = parse_date_param(date_str, default_to_today=False)
    if export_date is None:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Check if refined text file exists
    refined_path = get_refined_text_path(export_date)

    if not refined_path.exists():
        return jsonify({'error': f'Refined text file not found for {date_str}. Please generate refined text first.'}), 404

    try:
        # Build the activity graph
        nodes = build_activity_tree(str(refined_path))

        if not nodes:
            return jsonify({'error': 'Failed to build activity graph. No activities found.'}), 500

        # Convert to JSON-serializable dict (with full content for API)
        tree_data = tree_to_dict(nodes, truncate_content=False)

        # Save to data folder
        tree_path = get_activity_tree_path(export_date)
        if not write_json_file(tree_path, tree_data):
            return jsonify({'error': 'Failed to save tree file'}), 500

        return jsonify({
            'success': True,
            'tree': tree_data,
            'filename': tree_path.name
        })

    except Exception as e:
        return jsonify({'error': f'Failed to generate activity graph: {str(e)}'}), 500

@app.route('/api/weekly-activity')
def weekly_activity():
    """Get hourly keystroke data for the last 7 days."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Calculate date range (last 7 days including today)
        today = date.today()
        start_date = today - timedelta(days=6)  # 7 days total (today + 6 previous days)

        # Get hourly activity for last 7 days
        weekly_data = cursor.execute(f'''
            SELECT DATE(timestamp) as date, hour, SUM(keystrokes) as total_keystrokes
            FROM {DB_TABLE_ACTIVITY_LOG}
            WHERE DATE(timestamp) >= ? AND DATE(timestamp) <= ?
            GROUP BY DATE(timestamp), hour
            ORDER BY date DESC, hour ASC
        ''', (start_date.isoformat(), today.isoformat())).fetchall()

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
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)