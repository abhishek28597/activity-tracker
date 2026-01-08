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

## LLM Refiner (`llm_refiner.py`)

### Purpose

Provides text refinement capabilities using Groq's Llama 3.3 70B model to transform raw keystroke logs into clean, structured, grammatically correct text.

### Function: `refine_text(raw_text: str) -> str`

**Input:**
- Raw text reconstructed from keystrokes (with timestamps and intervals)

**Process:**
1. Loads `GROQ_API_KEY` from environment variables (via `python-dotenv`)
2. Sends text to Groq API with system prompt instructing format:
   ```
   [timestamp]
   [app name]
   Refined text...
   ```
3. LLM processes and returns refined text

**Output:**
- Clean, structured text with timestamps, app names, and refined content
- Falls back to original text if API call fails

**Configuration:**
- Model: `llama-3.3-70b-versatile`
- Temperature: `0.3` (for consistent formatting)
- Max tokens: `4096`

**Error Handling:**
- If API call fails, returns original text with error message prepended
- Logs errors to console for debugging

---

## Web Dashboard (`webapp.py`)

### Flask Routes

#### `GET /` — Dashboard

Returns the main dashboard HTML page with activity data for a selected date.

**Query Parameters:**
- `date` (optional): Date in `YYYY-MM-DD` format. Defaults to today.

#### `GET /api/export-keystrokes` — Export Keystrokes

Exports keystrokes as a downloadable text file with reconstructed readable text.

**Query Parameters:**
- `date` (required): Date in `YYYY-MM-DD` format
- `refine` (optional): If `true`, passes text through LLM refinement pipeline. Default: `false`

**Response:** 
- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="{date}_key_stroke.txt"` or `"{date}_refined_key_stroke.txt"` (if refined)

**Export Format (Standard):**
```
8 Jan 2026 at 1:00 PM
reconstructed text from keystrokes...

8 Jan 2026 at 1:30 PM  
more reconstructed text...
```

**Export Format (Refined):**
```
[8 Jan 2026 at 1:00 PM]
[App Name]
Refined, grammatically correct text with proper formatting.

[8 Jan 2026 at 1:30 PM]
[Another App]
More refined content...
```

**Text Reconstruction Logic:**
- Character keys are concatenated into words
- `backspace` removes the previous character
- `space` becomes a space character
- `enter` becomes a newline
- Modifier keys (shift, ctrl, alt, cmd) are ignored
- Navigation keys (arrows, home, end, etc.) are ignored
- Keystrokes are grouped into 30-minute intervals
- Empty intervals are skipped

**LLM Refinement (when `refine=true`):**
- Uses Groq's Llama 3.3 70B model via `llm_refiner.py`
- Requires `GROQ_API_KEY` environment variable
- Fixes typos and grammatical errors
- Groups related content by app and timestamp
- Formats commands and code snippets appropriately
- Removes gibberish or accidental keystrokes
- Outputs structured format: `[timestamp]\n[app]\nrefined text`

### Data Queries

**Hourly Activity (for Activity Timeline chart):**
```sql
SELECT hour, SUM(keystrokes), SUM(clicks)
FROM activity_log
WHERE DATE(timestamp) = ?  -- selected_date parameter
GROUP BY hour
ORDER BY hour
```

**Top Apps:**
```sql
SELECT app_name, SUM(keystrokes), SUM(clicks), COUNT(*) as minutes_active
FROM activity_log
WHERE DATE(timestamp) = ?  -- selected_date parameter
GROUP BY app_name
ORDER BY minutes_active DESC
LIMIT 10
```

**Recent Keystrokes (for modal, newest 500):**
```sql
SELECT timestamp, key_pressed, app_name
FROM keystroke_log
WHERE DATE(timestamp) = ?  -- selected_date parameter
ORDER BY timestamp DESC
LIMIT 500
```
*Note: Results are reversed in Python to display oldest-to-newest in the UI*

### Template Rendering

Data is passed to `templates/dashboard.html`:

```python
return render_template('dashboard.html',
    hourly_keystrokes=json.dumps(keystrokes_by_hour),
    hourly_keystrokes_list=keystrokes_by_hour,  # For chart rendering
    hourly_clicks=json.dumps(clicks_by_hour),
    app_usage=app_usage,
    total_activity=total_activity,
    most_productive=most_productive,
    recent_keystrokes=recent_keystrokes,
    selected_date=selected_date,
    today=today,
    is_today=(selected_date == today)
)
```

---

## Dashboard UI (`templates/dashboard.html`)

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│ Header: [Logo] Activity Tracker    [← Date Picker →] [View Keystrokes] │
├─────────────────────────────────────────────────────────────┤
│ Metrics Grid: [Keystrokes] [Clicks] [Active Hours] [Peak Hour]         │
├────────────────────────────────────┬────────────────────────┤
│ Activity Timeline (Area Chart)     │ Top Apps               │
│ - Hourly keystroke visualization   │ - App rankings         │
│ - Peak indicator                   │ - Keystroke/click counts│
└────────────────────────────────────┴────────────────────────┘
```

### Date Picker

Allows viewing historical data:
- Native HTML date input with max date = today
- Navigation arrows (← →) for day-by-day browsing
- "Today" button to jump back to current date
- URL parameter: `/?date=YYYY-MM-DD`

### Activity Timeline Chart

Pure CSS/SVG area chart showing hourly keystroke distribution:

```jinja2
<svg class="chart-svg" viewBox="0 0 720 200">
    <!-- Gradient fill definition -->
    <defs>
        <linearGradient id="areaGradient">
            <stop offset="0%" style="stop-color: #3fb950; stop-opacity: 0.4" />
            <stop offset="100%" style="stop-color: #3fb950; stop-opacity: 0.05" />
        </linearGradient>
    </defs>
    
    <!-- Area polygon generated from hourly_keystrokes_list -->
    <polygon class="chart-area" points="..." />
    <polyline class="chart-line" points="..." />
    
    <!-- Interactive data points with tooltips -->
    {% for val in hourly_data %}
        <circle class="chart-dot" cx="..." cy="..." 
                onmouseenter="showTooltip(...)" />
    {% endfor %}
</svg>
```

### Keystroke Stream Modal

Triggered by "View Keystrokes" button in header:

```
┌─────────────────────────────────────────────────┐
│ ⌨️ Keystroke Stream        [Export ▾] [×]      │
├─────────────────────────────────────────────────┤
│ Cursor  2026-01-08 15:35                        │
│ [h][e][l][l][o][space][w][o][r][l][d][enter]   │
│                                                 │
│ Chrome  2026-01-08 15:36                        │
│ [g][o][o][g][l][e][enter]                      │
└─────────────────────────────────────────────────┘
```

**Features:**
- Backdrop blur overlay
- Scrollable content (up to 500 keystrokes)
- Close via × button, Escape key, or clicking outside
- Export dropdown with date picker

### Export Dropdown

Inside the modal header:
- Date picker to select export date
- "Download TXT" button triggers `/api/export-keystrokes`
- Downloads file: `{date}_key_stroke.txt`

### Key Styling Classes

- `.key` — Default key appearance (dark background)
- `.key.special` — Blue highlight for Enter, Backspace, Tab, etc.
- `.key.modifier` — Purple highlight for Shift, Ctrl, Alt, Cmd
- `.key.space` — Wider badge for spacebar (shows ␣)

---

## Data Flow Summary

### Activity Tracking Flow

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
```

### Dashboard Viewing Flow

```
5. User opens localhost:5000/?date=2026-01-08
   │
   ▼
6. webapp.py queries database for selected date
   ├── Get activity_log for metrics & hourly chart
   └── Get keystroke_log for modal stream (newest 500)
   │
   ▼
7. Render dashboard.html with:
   ├── Metrics cards
   ├── Activity Timeline chart (hourly data)
   ├── Top Apps list
   └── Keystroke modal (hidden until opened)
```

### Export Flow

```
8. User clicks Export → selects date → Download TXT
   │
   ▼
9. GET /api/export-keystrokes?date=2026-01-08
   │
   ▼
10. webapp.py queries keystroke_log for date
    │
    ▼
11. Group keystrokes into 30-minute intervals
    │
    ▼
12. Reconstruct readable text:
    ├── Concatenate characters
    ├── Apply backspaces
    ├── Convert space/enter to whitespace
    └── Skip modifier/navigation keys
    │
    ▼
13. If refine=true:
    ├── Pass reconstructed text to llm_refiner.refine_text()
    ├── LLM processes and returns refined text
    └── Filename: "2026-01-08_refined_key_stroke.txt"
    │
    ▼
14. Return text file: "2026-01-08_key_stroke.txt" or "2026-01-08_refined_key_stroke.txt"
```

---

## Performance Considerations

- **Buffering:** Keystrokes are buffered in memory and batch-inserted every 60 seconds to minimize disk I/O
- **SQLite:** Good for single-user local storage; no server setup required
- **Limit 500:** Keystroke stream is limited to newest 500 entries to prevent UI slowdown
- **Date filtering:** All queries filter by selected date using indexed `DATE(timestamp)` for fast lookups
- **Modal on-demand:** Keystroke stream is hidden by default (in modal), reducing initial render time
- **Pure CSS chart:** Activity Timeline uses CSS/SVG without external charting libraries
- **Lazy export:** Keystroke text reconstruction only happens when export is requested
- **LLM refinement:** Optional refinement via Groq API (only when `refine=true` parameter is used)

---

## Security & Privacy

⚠️ **This tool captures ALL keystrokes including passwords!**

Recommendations:
- Don't run on shared computers
- Periodically clear the database: `rm activity.db`
- Consider adding app exclusion list (e.g., skip password managers)
- Database is stored locally and never transmitted

