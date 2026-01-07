# Activity Tracker

A macOS productivity tool that tracks your keyboard and mouse activity across applications, providing insights into how you spend your time.

![Activity Tracker Dashboard](assets/screenshot.png)

## Features

- **Real-time Keystroke Logging** - Captures every keystroke with timestamp and active application
- **Mouse Click Tracking** - Counts mouse clicks throughout the day
- **Per-Application Stats** - See which apps you use most based on actual typing activity
- **Keystroke Stream Visualization** - Visual display of your recent keystrokes grouped by application
- **Daily Metrics** - Total keystrokes, clicks, active hours, and peak productivity hour
- **Beautiful Dashboard** - Dark-themed web UI with real-time data visualization

## Requirements

- macOS (uses AppleScript for active window detection)
- Python 3.x
- Accessibility permissions (for keyboard/mouse monitoring)

## Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd activity-tracker
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install flask pynput pyobjc-framework-Cocoa
   ```

4. Grant Accessibility permissions:
   - Go to **System Preferences → Security & Privacy → Privacy → Accessibility**
   - Add your terminal app (Terminal, iTerm, or IDE)

## Usage

### Start the Activity Tracker

```bash
python tracker.py
```

This runs in the background and logs activity to `activity.db` every 60 seconds.

### View the Dashboard

In a separate terminal:

```bash
python webapp.py
```

Open your browser to [http://localhost:5000](http://localhost:5000)

## How It Works

### Data Collection (`tracker.py`)

- Uses `pynput` to listen for keyboard and mouse events
- Detects the active application using AppleScript
- Buffers individual keystrokes with their timestamps and source app
- Every 60 seconds, saves:
  - Individual keystrokes to `keystroke_log` table
  - Aggregated stats per-app to `activity_log` table

### Web Dashboard (`webapp.py`)

- Flask-based web server
- Queries SQLite database for today's activity
- Displays:
  - **Metrics cards**: Total keystrokes, clicks, active hours, peak hour
  - **Keystroke stream**: Recent keystrokes grouped by application
  - **Top Apps**: Applications ranked by activity time

## Database Schema

### `activity_log`
| Column | Type | Description |
|--------|------|-------------|
| timestamp | DATETIME | When the activity was logged |
| hour | INTEGER | Hour of day (0-23) |
| app_name | TEXT | Application name |
| keystrokes | INTEGER | Number of keystrokes |
| clicks | INTEGER | Number of mouse clicks |

### `keystroke_log`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-increment ID |
| timestamp | DATETIME | When the key was pressed |
| key_pressed | TEXT | The key that was pressed |
| app_name | TEXT | Active application |

## Project Structure

```
activity-tracker/
├── tracker.py          # Background activity monitor
├── webapp.py           # Flask web dashboard
├── activity.db         # SQLite database (auto-created)
├── templates/
│   └── dashboard.html  # Dashboard UI template
├── assets/
│   └── screenshot.png  # Dashboard screenshot
├── docs/
│   └── architecture.md # Detailed code documentation
└── venv/               # Python virtual environment
```

## Documentation

For detailed technical documentation including:
- System architecture diagrams
- Database schema details
- Code flow explanations
- Threading model
- Performance considerations

See [docs/architecture.md](docs/architecture.md)

## Privacy Note

⚠️ This tool logs all keystrokes locally. The data never leaves your machine and is stored in a local SQLite database. Be mindful that sensitive information (passwords, etc.) will be captured. Consider clearing the database periodically or adding exclusion rules for sensitive applications.

## License

MIT

