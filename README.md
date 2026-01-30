# AutoSchedule - Automatic Shift Scheduling Application

A powerful, user-friendly GUI application for managing employee schedules with intelligent auto-scheduling capabilities. Built with Python and Tkinter, AutoSchedule helps you efficiently assign staff to shifts while respecting availability constraints, workload limits, and conflict rules.

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## 🎯 Key Features

### 1. **User Profile Management**
- Add, edit, and delete user profiles with ease
- Set maximum shifts per week for each user (prevents overwork)
- **Interactive 7-day hourly availability grid** - click cells to toggle availability hour by hour
- Quick action buttons: "Select All", "Clear All", "Weekdays Only" for fast availability configuration
- Assign personalized colors to users for easy visual identification in the calendar
- Double-click any user to edit their profile instantly

### 2. **Two Types of Shifts**
- **📌 Fixed Shifts**: Time-sensitive shifts that cannot be moved during auto-scheduling (e.g., "Morning Reception 9-12")
  - Perfect for shifts with strict timing requirements
  - Scheduled first to ensure critical time slots are covered
- **🔄 Flexible Shifts**: Auto-adjusts to optimal time slots based on user availability
  - Automatically finds the best time window with maximum staff availability
  - Intelligently moves to times when more users can participate

### 3. **Conflict Management**
- Define pairs of users who cannot work together
- Conflicts are automatically respected during auto-scheduling
- Prevents scheduling incompatible team members on the same shift
- Easy-to-use conflict pair manager with visual interface

### 4. **Calendar View**
- Google Calendar-inspired weekly view for intuitive schedule visualization
- Color-coded shifts with visual distinction:
  - Pink background for Fixed shifts (📌)
  - Green background for Flexible shifts (🔄)
- Displays shift details: name, time range, and assigned users
- Responsive design that adapts to window resizing
- Hour-by-hour grid (8 AM - 6 PM) across all seven days

### 5. **Intelligent Auto-Scheduling**
- One-click automatic assignment of users to shifts
- **Smart workload balancing** - distributes shifts fairly across all users
- **Respects all constraints**:
  - User availability (won't assign users when they're unavailable)
  - Maximum shifts per week limits
  - Conflict pairs (incompatible users)
- **Flexible shift optimization** - moves flexible shifts to time slots with better availability
- Uses a sophisticated algorithm that:
  1. Schedules fixed shifts first (priority)
  2. Finds optimal time slots for flexible shifts
  3. Assigns users fairly while respecting all constraints

### 6. **Data Persistence**
- Automatically saves data to JSON files:
  - `users.json` - User profiles and availability
  - `shifts.json` - All shift definitions and assignments
  - `conflicts.json` - Conflict pair rules
- Data persists between sessions - pick up where you left off
- Manual save option available in File menu

## 🚀 How to Use

### Quick Start
1. Launch the application: `python scheduler_app.py`
2. **File → Load Sample Data** to see a demo with pre-populated users and shifts
3. Click the **+** buttons to add new users or shifts
4. Double-click any item to edit it
5. Click **🔄 Auto-Schedule** to automatically assign users to shifts
6. Data auto-saves when you make changes

### Detailed Workflow
1. **Set up Users**:
   - Click **+** in the Users panel
   - Enter name, set max shifts per week
   - Click cells in the availability grid to mark when each user is available
   - Use quick actions for common patterns (e.g., "Weekdays Only")
   - Assign a color for visual identification

2. **Create Shifts**:
   - Click **+** in the Shifts panel
   - Choose between Fixed (📌) or Flexible (🔄) shift type
   - Set day, start time, end time, and required staff count
   - Fixed shifts keep their time; Flexible shifts may be moved to optimal slots

3. **Define Conflicts** (Optional):
   - Click "Manage Conflict Pairs"
   - Select two users who cannot work together
   - These pairs will never be scheduled on the same shift

4. **Auto-Schedule**:
   - Click **Schedule → Auto-Schedule All**
   - Watch as the algorithm assigns users intelligently
   - Review assignments in the calendar view
   - Re-run if needed to try different assignments

5. **Manual Adjustments**:
   - Edit any shift to manually change assignments
   - The calendar updates in real-time

## 📋 Requirements

### System Requirements
- **Python**: 3.7 or higher
- **Operating System**: Windows, macOS, or Linux with GUI support

### Dependencies
All dependencies are part of Python's standard library - no external packages required!
- `tkinter` - GUI framework (usually included with Python)
- `json` - Data persistence
- `datetime` - Time handling
- `dataclasses` - Data models
- `typing` - Type hints
- `enum` - Enumerations
- `random` - Randomization for fair scheduling
- `copy` - Deep copying for safe data manipulation

## 🔧 Installation

1. **Ensure Python 3.7+ is installed**:
   ```bash
   python --version
   # or
   python3 --version
   ```

2. **Verify tkinter is available** (required for GUI):
   ```bash
   python -m tkinter
   # A small window should appear
   ```

   If tkinter is missing:
   - **Ubuntu/Debian**: `sudo apt-get install python3-tk`
   - **Fedora**: `sudo dnf install python3-tkinter`
   - **macOS**: Included with Python from python.org
   - **Windows**: Included with official Python installer

3. **Download or clone the repository**:
   ```bash
   git clone https://github.com/Copycatmax/autoScheduler.git
   cd autoScheduler
   ```

4. **Run the application**:
   ```bash
   python scheduler_app.py
   # or
   python3 scheduler_app.py
   ```

No additional installation steps required!

## 📁 File Structure

```
autoScheduler/
│
├── scheduler_app.py      # Main application file (all code)
├── users.json            # User profiles (auto-generated)
├── shifts.json           # Shift definitions (auto-generated)
├── conflicts.json        # Conflict pairs (auto-generated)
└── README.md             # This file
```

## 🏗️ Architecture Overview

### High-Level Architecture
The application follows a clean, modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    GUI Layer (Tkinter)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ SchedulerApp │  │  UserDialog  │  │ ShiftDialog  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────┐
│                   Business Logic Layer                   │
│  ┌──────────────┐        ┌───────────────────────┐     │
│  │  Scheduler   │        │    Data Validation    │     │
│  │   (Engine)   │        │   & Transformation    │     │
│  └──────────────┘        └───────────────────────┘     │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────┐
│                   Data Layer                             │
│  ┌──────────────┐        ┌───────────────────────┐     │
│  │ DataManager  │───────▶│   JSON Files          │     │
│  │              │        │ (users, shifts,       │     │
│  │              │        │  conflicts)           │     │
│  └──────────────┘        └───────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. **Data Models** (Lines 18-110)
Immutable, type-safe data structures using Python dataclasses:

- **`User`**: Represents an employee/staff member
  - Properties: name, max_shifts_per_week, availability (7-day hourly grid), color
  - Methods: `is_available(day, hour)` for availability checking
  - Serialization: `to_dict()` and `from_dict()` for JSON persistence

- **`Shift`**: Represents a work shift
  - Properties: id, name, shift_type (Fixed/Flexible), day, start_hour, end_hour, required_staff, assigned_users
  - Methods: `duration()` calculates shift length
  - Two types via `ShiftType` enum: FIXED and FLEXIBLE

- **`ShiftType`**: Enum defining shift behavior
  - FIXED: Cannot be moved during auto-scheduling
  - FLEXIBLE: Can be optimized to better time slots

#### 2. **DataManager** (Lines 117-177)
Handles all data persistence operations:
- **Save Operations**: Serializes objects to JSON with proper formatting
- **Load Operations**: Deserializes JSON to Python objects with error handling
- **Files Managed**:
  - `users.json`: User profiles and availability
  - `shifts.json`: Shift definitions and current assignments
  - `conflicts.json`: User conflict pairs
- **Error Resilience**: Returns empty collections on file errors (graceful degradation)

#### 3. **Scheduler Engine** (Lines 184-312)
The intelligent auto-scheduling algorithm:

**Key Methods**:
- `schedule_shifts(shifts)`: Main entry point for auto-scheduling
  - Returns new shift assignments without modifying originals
  - Processes fixed shifts first, then flexible shifts
  - Maintains workload balance across users

- `_assign_shift(shift, shifts_worked)`: Assigns users to a single shift
  - Finds available candidates
  - Sorts by current workload (fairness)
  - Checks conflict rules before assignment
  - Updates workload tracking

- `_find_best_slot(shift, shifts_worked)`: Optimizes flexible shift timing
  - Scans all possible day/time combinations
  - Scores each slot by available staff count
  - Returns slot with maximum availability
  - Only considers slots that meet minimum staff requirements

- `get_available_users(shift, shifts_worked)`: Filter users by constraints
  - Checks max shifts per week limit
  - Validates availability for all shift hours
  - Returns list of eligible candidates

- `has_conflict(assigned, candidate)`: Enforces conflict rules
  - Checks if candidate conflicts with any assigned user
  - Uses bidirectional conflict set for efficiency

**Scheduling Algorithm Flow**:
```
1. Separate shifts into Fixed and Flexible
2. For each Fixed shift:
   - Get available users (respecting max shifts and availability)
   - Sort by workload (fairness)
   - Assign users while checking conflicts
   - Update workload counter
3. For each Flexible shift:
   - Find optimal time slot (most available users)
   - Update shift time to optimal slot
   - Assign users (same process as Fixed)
4. Return updated shift list
```

#### 4. **SchedulerApp** (Lines 319-1067)
Main GUI application class managing the user interface:

**Key Features**:
- **Three-Panel Layout**:
  1. Left Panel: Users list with add/edit/delete controls
  2. Middle Panel: Shifts list with add/edit/delete controls
  3. Right Panel: Weekly calendar visualization

- **Menu System**:
  - File: Save All, Load Sample Data, Exit
  - Schedule: Auto-Schedule All, Clear All Assignments
  - Help: About

- **Calendar Rendering**:
  - `_draw_calendar()`: Main drawing method
  - Grid-based layout with time labels and day headers
  - Color-coded shifts (pink=fixed, green=flexible)
  - Displays shift details: name, time, assigned users
  - Responsive to window resizing

- **Event Handlers**:
  - User selection, double-click to edit
  - Shift selection, double-click to edit
  - Add/edit/delete operations with validation
  - Auto-save on data changes

#### 5. **Dialog Windows** (Lines 1073-1653)

**UserDialog** (Lines 1073-1290):
- Interactive 7-day × 11-hour availability grid
- Click cells to toggle availability (green=available, pink=unavailable)
- Quick action buttons:
  - "Select All": Mark all hours available
  - "Clear All": Mark all hours unavailable
  - "Weekdays Only": Available Monday-Friday, unavailable weekends
- Real-time color preview
- Input validation for name and max shifts

**ShiftDialog** (Lines 1292-1481):
- Create/edit shift details
- Type selector: Fixed vs. Flexible (radio buttons)
- Day dropdown (Monday-Sunday)
- Time selection: Start and end hour spinners
- Required staff count (1-10)
- Manual user assignment (multi-select listbox)
- Visual indicators for shift type (📌/🔄)

**ConflictDialog** (Lines 1484-1653):
- Manage user conflict pairs
- Two dropdowns for selecting users
- Add conflict button
- List of current conflicts
- Delete conflict button
- Prevents duplicate conflicts
- Updates scheduling constraints in real-time

### Design Patterns Used

1. **Model-View-Controller (MVC)**:
   - Model: Data classes (User, Shift) + DataManager
   - View: Tkinter GUI (SchedulerApp, Dialogs)
   - Controller: Event handlers and Scheduler logic

2. **Repository Pattern**:
   - DataManager abstracts data storage
   - Easy to swap JSON for database later

3. **Strategy Pattern**:
   - ShiftType enum enables different scheduling behaviors
   - Fixed vs. Flexible handled polymorphically

4. **Observer Pattern**:
   - GUI refreshes on data changes
   - `_refresh_all()` updates all views consistently

### Libraries and Technologies

**Core Libraries** (All Standard Library):
- **tkinter**: GUI framework
  - `ttk`: Themed widgets for modern look
  - `messagebox`: Dialog boxes
  - `simpledialog`: Input dialogs
- **json**: Data serialization/deserialization
- **dataclasses**: Clean data model definitions
- **typing**: Type hints for code clarity
- **datetime**: Date and time manipulation
- **enum**: Enumeration types
- **random**: Randomization for fair scheduling
- **copy**: Deep copying for immutable operations

**Why No External Dependencies?**
- Simplicity: Easy to install and run anywhere
- Portability: Works on any system with Python
- Reliability: No dependency conflicts or version issues
- Lightweight: Small footprint, fast startup

## 🧪 Testing

To test the application:

1. **Load Sample Data**: File → Load Sample Data
   - Creates 5 sample users (Alice, Bob, Charlie, Diana, Eve)
   - Creates 5 sample shifts (mix of fixed and flexible)
   - Sets up one conflict pair (Alice and Bob)

2. **Try Auto-Scheduling**: Schedule → Auto-Schedule All
   - Observe how users are assigned
   - Check that conflicts are respected
   - Verify workload is balanced

3. **Manual Testing Scenarios**:
   - Add a user with limited availability
   - Create overlapping shifts
   - Set up multiple conflicts
   - Test flexible shift optimization

## 🤝 Contributing

Contributions are welcome! Here are some ideas:
- Add export to iCal/CSV
- Implement shift templates
- Add user roles and permissions
- Multi-week scheduling
- Shift swap requests
- Email notifications
- Dark mode theme

## 📝 License

MIT License - feel free to use and modify for your needs.

## 🐛 Troubleshooting

**Issue**: "No module named 'tkinter'"
- **Solution**: Install tkinter for your OS (see Installation section)

**Issue**: Data not saving
- **Solution**: Ensure write permissions in the application directory

**Issue**: Application window too small/large
- **Solution**: Resize the window - layout is responsive. Minimum size is 1200x700.

**Issue**: Auto-schedule assigns no one
- **Solution**: Check that users have availability matching shift times and haven't exceeded max shifts

## 📞 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing issues for solutions

---

**Made with ❤️ for efficient workforce scheduling**