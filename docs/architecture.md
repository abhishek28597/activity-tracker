# Activity Tracker - Architecture & Code Documentation

This document explains how the Activity Tracker works under the hood.

## Overview

The Activity Tracker consists of two main components:

1. **Tracker (`tracker.py`)** - Background daemon that monitors keyboard/mouse activity
2. **Web Dashboard (`webapp.py`)** - Flask server that displays activity data

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   tracker.py    │────▶│  activity.db │◀────│   webapp.py     │
│  (background)   │     │   (SQLite)   │     │  (Flask server) │
└─────────────────┘     └──────────────┘     └─────────────────┘
        │                                            │
        ▼                                            ▼
  Keyboard/Mouse                              Web Dashboard
    Listeners                                 localhost:5000
```

---

## Database Schema

The SQLite database (`activity.db`) contains two tables:

### `activity_log` — Aggregated Activity

Stores summarized activity data, saved every 60 seconds.

```sql
CREATE TABLE IF NOT EXISTS activity_log (
    timestamp DATETIME,
    hour INTEGER,
    app_name TEXT,
    keystrokes INTEGER,
    clicks INTEGER
)
```

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | DATETIME | When the activity was logged |
| `hour` | INTEGER | Hour of day (0-23) for hourly grouping |
| `app_name` | TEXT | Application where activity occurred |
| `keystrokes` | INTEGER | Keystroke count for that app |
| `clicks` | INTEGER | Mouse click count |

**Used for:** Top Apps panel, daily metrics, hourly charts

### `keystroke_log` — Individual Keystrokes

Stores every single keystroke with its context.

```sql
CREATE TABLE IF NOT EXISTS keystroke_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    key_pressed TEXT,
    app_name TEXT
)
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-incrementing primary key |
| `timestamp` | DATETIME | Exact time the key was pressed |
| `key_pressed` | TEXT | The key (e.g., `a`, `enter`, `shift`) |
| `app_name` | TEXT | Active application when pressed |

**Used for:** Keystroke Stream visualization

---

## Tracker (`tracker.py`)

### Class: `ActivityTracker`

The main class that handles all activity monitoring.

### Initialization Flow

```python
def __init__(self):
    self.keystroke_count = 0      # Running count of keystrokes
    self.mouse_clicks = 0         # Running count of clicks
    self.current_app = ""         # Currently active application
    self.keystroke_buffer = []    # Buffer storing individual keystrokes
    self.init_database()          # Create tables if not exist
    self.start_tracking()         # Start listeners and save thread
```

### Active Window Detection

Uses AppleScript to get the frontmost application name:

```python
def get_active_app(self):
    script = '''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    '''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    return result.stdout.strip()
```

**Note:** This is macOS-specific. For cross-platform support, you'd need platform-specific implementations.

### Keystroke Handling

When a key is pressed:

```python
def on_key_press(self, key):
    self.keystroke_count += 1
    
    # Convert key to readable string
    key_str = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
    
    # Buffer the keystroke with metadata
    self.keystroke_buffer.append({
        'timestamp': datetime.now(),
        'key': key_str,
        'app': self.get_active_app()
    })
```

**Key conversion examples:**
- Regular keys: `'a'`, `'1'`, `'@'`
- Special keys: `'enter'`, `'shift'`, `'backspace'`
- Modifier keys: `'ctrl'`, `'alt'`, `'cmd'`

### Data Persistence (Every 60 Seconds)

The `save_activity()` method runs in a background thread:

```python
def save_activity(self):
    while True:
        time.sleep(60)  # Save every minute
        
        # Aggregate keystrokes by app from buffer
        app_keystrokes = {}
        for keystroke in self.keystroke_buffer:
            app = keystroke['app']
            app_keystrokes[app] = app_keystrokes.get(app, 0) + 1
        
        # Save individual keystrokes to keystroke_log
        for keystroke in self.keystroke_buffer:
            # INSERT INTO keystroke_log ...
        
        # Save aggregated stats to activity_log (one row per app)
        for app, key_count in app_keystrokes.items():
            # INSERT INTO activity_log ...
        
        # Reset counters and buffer
        self.keystroke_count = 0
        self.mouse_clicks = 0
        self.keystroke_buffer = []
```

**Why aggregate by app?** 
If you type in Cursor, then switch to Chrome, both apps get credited with their actual keystroke counts (not just whatever app is active at save time).

### Threading Model

```
Main Thread
    │
    ├── Keyboard Listener (pynput) ──▶ on_key_press()
    │
    ├── Mouse Listener (pynput) ──▶ on_click()
    │
    └── Save Thread (daemon) ──▶ save_activity() [every 60s]
```

---

## Web Dashboard (`webapp.py`)

### Flask Routes

#### `GET /` — Dashboard

Returns the main dashboard HTML page with today's activity data.

### Data Queries

**Hourly Activity:**
```sql
SELECT hour, SUM(keystrokes), SUM(clicks)
FROM activity_log
WHERE DATE(timestamp) = DATE('now', 'localtime')
GROUP BY hour
ORDER BY hour
```

**Top Apps:**
```sql
SELECT app_name, SUM(keystrokes), SUM(clicks), COUNT(*) as minutes_active
FROM activity_log
WHERE DATE(timestamp) = DATE('now', 'localtime')
GROUP BY app_name
ORDER BY minutes_active DESC
LIMIT 10
```

**Recent Keystrokes:**
```sql
SELECT timestamp, key_pressed, app_name
FROM keystroke_log
WHERE DATE(timestamp) = DATE('now', 'localtime')
ORDER BY timestamp ASC
LIMIT 200
```

### Template Rendering

Data is passed to `templates/dashboard.html`:

```python
return render_template('dashboard.html',
    hourly_keystrokes=json.dumps(keystrokes_by_hour),
    hourly_clicks=json.dumps(clicks_by_hour),
    app_usage=app_usage,
    total_activity=total_activity,
    most_productive=most_productive,
    recent_keystrokes=recent_keystrokes,
    today=today
)
```

---

## Dashboard UI (`templates/dashboard.html`)

### Keystroke Stream Visualization

Groups consecutive keystrokes by application:

```jinja2
{% for keystroke in recent_keystrokes %}
    {% if keystroke['app_name'] != current_app.value %}
        <!-- New app group header -->
        <div class="keystroke-group">
            <span class="app-name">{{ keystroke['app_name'] }}</span>
            <span>{{ keystroke['timestamp'] }}</span>
        </div>
    {% endif %}
    
    <!-- Key badge with styling based on key type -->
    {% if key in ['shift', 'ctrl', 'alt', 'cmd'] %}
        <span class="key modifier">{{ key }}</span>
    {% elif key in ['enter', 'backspace', 'tab'] %}
        <span class="key special">{{ key }}</span>
    {% else %}
        <span class="key">{{ key }}</span>
    {% endif %}
{% endfor %}
```

### Key Styling Classes

- `.key` — Default key appearance
- `.key.special` — Blue highlight for Enter, Backspace, Tab, etc.
- `.key.modifier` — Purple highlight for Shift, Ctrl, Alt, Cmd
- `.key.space` — Wider badge for spacebar

---

## Data Flow Summary

```
1. User presses 'H' in Cursor
   │
   ▼
2. pynput captures keypress
   │
   ▼
3. on_key_press() called
   ├── Increment keystroke_count
   ├── Get active app ("Cursor")
   └── Add to buffer: {timestamp, key: 'h', app: 'Cursor'}
   │
   ▼
4. After 60 seconds, save_activity() runs
   ├── Aggregate buffer by app
   ├── INSERT each keystroke into keystroke_log
   ├── INSERT app totals into activity_log
   └── Clear buffer and counters
   │
   ▼
5. User opens localhost:5000
   │
   ▼
6. webapp.py queries database
   ├── Get today's activity_log for metrics
   └── Get today's keystroke_log for stream
   │
   ▼
7. Render dashboard.html with data
```

---

## Performance Considerations

- **Buffering:** Keystrokes are buffered in memory and batch-inserted every 60 seconds to minimize disk I/O
- **SQLite:** Good for single-user local storage; no server setup required
- **Limit 200:** Keystroke stream is limited to prevent UI slowdown with heavy typing
- **Date filtering:** All queries filter by today's date to keep results fast

---

## Security & Privacy

⚠️ **This tool captures ALL keystrokes including passwords!**

Recommendations:
- Don't run on shared computers
- Periodically clear the database: `rm activity.db`
- Consider adding app exclusion list (e.g., skip password managers)
- Database is stored locally and never transmitted

