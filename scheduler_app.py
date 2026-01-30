"""
AutoSchedule - Automatic Shift Scheduling Application
A GUI application for managing user profiles, shifts, and automatic scheduling.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Tuple, Optional
from enum import Enum
import random
import copy


# ============================================================================
# DATA MODELS
# ============================================================================

class ShiftType(Enum):
    """Enum for shift types."""
    FIXED = "fixed"
    FLEXIBLE = "flexible"


@dataclass
class User:
    """Represents a user/employee with availability settings."""
    name: str
    max_shifts_per_week: int = 5
    # Availability: dict mapping day (0-6) to list of available hours (0-23)
    availability: Dict[int, List[int]] = field(default_factory=dict)
    color: str = "#4A90D9"

    def __post_init__(self):
        """Initialize default availability (all business hours available)."""
        if not self.availability:
            for day in range(7):
                self.availability[day] = list(range(8, 18))  # 8am to 6pm

    def is_available(self, day: int, hour: int) -> bool:
        """Check if user is available at specific day and hour."""
        day_key = str(day) if isinstance(list(self.availability.keys())[0], str) else day
        return hour in self.availability.get(day_key, [])

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'max_shifts_per_week': self.max_shifts_per_week,
            'availability': {str(k): v for k, v in self.availability.items()},
            'color': self.color
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create User from dictionary."""
        availability = {int(k): v for k, v in data.get('availability', {}).items()}
        return cls(
            name=data['name'],
            max_shifts_per_week=data.get('max_shifts_per_week', 5),
            availability=availability,
            color=data.get('color', '#4A90D9')
        )


@dataclass
class Shift:
    """Represents a shift that needs to be staffed."""
    id: str
    name: str
    shift_type: ShiftType
    day: int  # 0=Monday, 6=Sunday
    start_hour: int
    end_hour: int
    required_staff: int = 1
    assigned_users: List[str] = field(default_factory=list)

    def duration(self) -> int:
        """Return shift duration in hours."""
        return self.end_hour - self.start_hour

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'shift_type': self.shift_type.value,
            'day': self.day,
            'start_hour': self.start_hour,
            'end_hour': self.end_hour,
            'required_staff': self.required_staff,
            'assigned_users': self.assigned_users
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Shift':
        """Create Shift from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            shift_type=ShiftType(data['shift_type']),
            day=data['day'],
            start_hour=data['start_hour'],
            end_hour=data['end_hour'],
            required_staff=data.get('required_staff', 1),
            assigned_users=data.get('assigned_users', [])
        )


# ============================================================================
# DATA MANAGER
# ============================================================================

class DataManager:
    """Handles data persistence for users and shifts."""

    def __init__(self, data_dir: str = None):
        """Initialize data manager with storage directory."""
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, 'users.json')
        self.shifts_file = os.path.join(data_dir, 'shifts.json')
        self.conflicts_file = os.path.join(data_dir, 'conflicts.json')

    def save_users(self, users: Dict[str, User]) -> None:
        """Save users to JSON file."""
        data = {name: user.to_dict() for name, user in users.items()}
        with open(self.users_file, 'w') as f:
            json.dump(data, f, indent=2)

    def load_users(self) -> Dict[str, User]:
        """Load users from JSON file."""
        if not os.path.exists(self.users_file):
            return {}
        try:
            with open(self.users_file, 'r') as f:
                data = json.load(f)
            return {name: User.from_dict(user_data) for name, user_data in data.items()}
        except (json.JSONDecodeError, KeyError):
            return {}

    def save_shifts(self, shifts: List[Shift]) -> None:
        """Save shifts to JSON file."""
        data = [shift.to_dict() for shift in shifts]
        with open(self.shifts_file, 'w') as f:
            json.dump(data, f, indent=2)

    def load_shifts(self) -> List[Shift]:
        """Load shifts from JSON file."""
        if not os.path.exists(self.shifts_file):
            return []
        try:
            with open(self.shifts_file, 'r') as f:
                data = json.load(f)
            return [Shift.from_dict(shift_data) for shift_data in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def save_conflicts(self, conflicts: List[Tuple[str, str]]) -> None:
        """Save conflict pairs to JSON file."""
        with open(self.conflicts_file, 'w') as f:
            json.dump(conflicts, f, indent=2)

    def load_conflicts(self) -> List[Tuple[str, str]]:
        """Load conflict pairs from JSON file."""
        if not os.path.exists(self.conflicts_file):
            return []
        try:
            with open(self.conflicts_file, 'r') as f:
                data = json.load(f)
            return [tuple(pair) for pair in data]
        except (json.JSONDecodeError, KeyError):
            return []


# ============================================================================
# SCHEDULER ENGINE
# ============================================================================

class Scheduler:
    """Handles automatic scheduling logic."""

    def __init__(
        self,
        users: Dict[str, User],
        conflicts: List[Tuple[str, str]]
    ):
        """Initialize scheduler with users and conflict rules."""
        self.users = users
        self.conflicts = set()
        for pair in conflicts:
            self.conflicts.add((pair[0], pair[1]))
            self.conflicts.add((pair[1], pair[0]))

    def has_conflict(self, assigned: List[str], candidate: str) -> bool:
        """Check if candidate conflicts with any assigned user."""
        for user in assigned:
            if (user, candidate) in self.conflicts:
                return True
        return False

    def get_available_users(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int]
    ) -> List[str]:
        """Get list of users available for a shift."""
        candidates = []
        for name, user in self.users.items():
            # Check max shifts
            if shifts_worked.get(name, 0) >= user.max_shifts_per_week:
                continue
            # Check availability for all hours of the shift
            available = True
            for hour in range(shift.start_hour, shift.end_hour):
                if not user.is_available(shift.day, hour):
                    available = False
                    break
            if available:
                candidates.append(name)
        return candidates

    def schedule_shifts(self, shifts: List[Shift]) -> List[Shift]:
        """
        Automatically assign users to shifts.
        Fixed shifts are scheduled first, then flexible shifts.
        """
        # Work with copies to avoid modifying originals
        scheduled_shifts = [copy.deepcopy(s) for s in shifts]

        # Track shifts worked per user
        shifts_worked = {name: 0 for name in self.users}

        # Separate fixed and flexible shifts
        fixed_shifts = [s for s in scheduled_shifts if s.shift_type == ShiftType.FIXED]
        flexible_shifts = [s for s in scheduled_shifts if s.shift_type == ShiftType.FLEXIBLE]

        # Schedule fixed shifts first (they can't be moved)
        for shift in fixed_shifts:
            self._assign_shift(shift, shifts_worked)

        # Schedule flexible shifts (could potentially optimize timing)
        for shift in flexible_shifts:
            # Try to find optimal time slot based on availability
            best_slot = self._find_best_slot(shift, shifts_worked)
            if best_slot:
                shift.day, shift.start_hour, shift.end_hour = best_slot
            self._assign_shift(shift, shifts_worked)

        return scheduled_shifts

    def _assign_shift(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int]
    ) -> None:
        """Assign users to a single shift."""
        shift.assigned_users = []
        candidates = self.get_available_users(shift, shifts_worked)

        # Shuffle for fairness, then sort by workload
        random.shuffle(candidates)
        candidates.sort(key=lambda u: shifts_worked.get(u, 0))

        for candidate in candidates:
            if len(shift.assigned_users) >= shift.required_staff:
                break
            if not self.has_conflict(shift.assigned_users, candidate):
                shift.assigned_users.append(candidate)
                shifts_worked[candidate] = shifts_worked.get(candidate, 0) + 1

    def _find_best_slot(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int]
    ) -> Optional[Tuple[int, int, int]]:
        """
        Find the best time slot for a flexible shift.
        Returns (day, start_hour, end_hour) or None.
        """
        duration = shift.duration()
        best_slot = None
        best_score = -1

        # Try each day and hour
        for day in range(7):
            for start_hour in range(8, 18 - duration + 1):
                end_hour = start_hour + duration

                # Count available users for this slot
                available_count = 0
                for name, user in self.users.items():
                    if shifts_worked.get(name, 0) >= user.max_shifts_per_week:
                        continue
                    available = True
                    for hour in range(start_hour, end_hour):
                        if not user.is_available(day, hour):
                            available = False
                            break
                    if available:
                        available_count += 1

                # Score based on available users
                if available_count >= shift.required_staff and available_count > best_score:
                    best_score = available_count
                    best_slot = (day, start_hour, end_hour)

        return best_slot


# ============================================================================
# GUI APPLICATION
# ============================================================================

class SchedulerApp:
    """Main application window."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    HOURS = list(range(8, 19))  # 8am to 6pm

    # Color palette for users
    USER_COLORS = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]

    def __init__(self, root: tk.Tk):
        """Initialize the application."""
        self.root = root
        self.root.title("AutoSchedule - Shift Scheduling Application")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)

        # Data
        self.data_manager = DataManager()
        self.users: Dict[str, User] = self.data_manager.load_users()
        self.shifts: List[Shift] = self.data_manager.load_shifts()
        self.conflicts: List[Tuple[str, str]] = self.data_manager.load_conflicts()

        # UI State
        self.selected_user: Optional[str] = None
        self.shift_counter = len(self.shifts)

        # Setup UI
        self._setup_styles()
        self._create_menu()
        self._create_main_layout()
        self._refresh_all()

    def _setup_styles(self) -> None:
        """Configure ttk styles."""
        style = ttk.Style()
        style.theme_use('clam')

        # Configure custom styles
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
        style.configure('Subheader.TLabel', font=('Segoe UI', 11, 'bold'))
        style.configure('Card.TFrame', background='white', relief='solid')
        style.configure(
            'Action.TButton',
            font=('Segoe UI', 10),
            padding=(10, 5)
        )
        style.configure(
            'Primary.TButton',
            font=('Segoe UI', 10, 'bold'),
            padding=(15, 8)
        )

    def _create_menu(self) -> None:
        """Create application menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save All", command=self._save_all)
        file_menu.add_command(label="Load Sample Data", command=self._load_sample_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Schedule menu
        schedule_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Schedule", menu=schedule_menu)
        schedule_menu.add_command(
            label="Auto-Schedule All",
            command=self._auto_schedule
        )
        schedule_menu.add_command(
            label="Clear All Assignments",
            command=self._clear_assignments
        )

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self) -> None:
        """Create main application layout."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel (Users and Shifts)
        left_panel = ttk.Frame(main_frame, width=350)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        # Users section
        self._create_users_panel(left_panel)

        # Shifts section
        self._create_shifts_panel(left_panel)

        # Right panel (Calendar)
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_calendar_panel(right_panel)

    def _create_users_panel(self, parent: ttk.Frame) -> None:
        """Create the users management panel."""
        # Header
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(
            header_frame,
            text="👤 Users",
            style='Header.TLabel'
        ).pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame,
            text="+",
            width=3,
            command=self._add_user
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="✎",
            width=3,
            command=self._edit_user
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="🗑",
            width=3,
            command=self._delete_user
        ).pack(side=tk.LEFT, padx=2)

        # Users listbox
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.users_listbox = tk.Listbox(
            list_frame,
            font=('Segoe UI', 10),
            selectmode=tk.SINGLE,
            activestyle='none',
            highlightthickness=1,
            highlightcolor='#4A90D9'
        )
        self.users_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.users_listbox.bind('<<ListboxSelect>>', self._on_user_select)
        self.users_listbox.bind('<Double-Button-1>', lambda e: self._edit_user())

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient=tk.VERTICAL,
            command=self.users_listbox.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_listbox.config(yscrollcommand=scrollbar.set)

        # Conflict pairs button
        ttk.Button(
            parent,
            text="Manage Conflict Pairs",
            command=self._manage_conflicts
        ).pack(fill=tk.X, pady=(0, 10))

    def _create_shifts_panel(self, parent: ttk.Frame) -> None:
        """Create the shifts management panel."""
        # Header
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(
            header_frame,
            text="📅 Shifts",
            style='Header.TLabel'
        ).pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame,
            text="+",
            width=3,
            command=self._add_shift
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="✎",
            width=3,
            command=self._edit_shift
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="🗑",
            width=3,
            command=self._delete_shift
        ).pack(side=tk.LEFT, padx=2)

        # Shifts listbox
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.shifts_listbox = tk.Listbox(
            list_frame,
            font=('Segoe UI', 10),
            selectmode=tk.SINGLE,
            activestyle='none',
            highlightthickness=1
        )
        self.shifts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.shifts_listbox.bind('<Double-Button-1>', lambda e: self._edit_shift())

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient=tk.VERTICAL,
            command=self.shifts_listbox.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.shifts_listbox.config(yscrollcommand=scrollbar.set)

        # Auto-schedule button
        ttk.Button(
            parent,
            text="🔄 Auto-Schedule",
            style='Primary.TButton',
            command=self._auto_schedule
        ).pack(fill=tk.X, pady=(5, 0))

    def _create_calendar_panel(self, parent: ttk.Frame) -> None:
        """Create the calendar view panel."""
        # Header
        ttk.Label(
            parent,
            text="📆 Weekly Schedule",
            style='Header.TLabel'
        ).pack(anchor=tk.W, pady=(0, 10))

        # Calendar canvas with scrollbars
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.calendar_canvas = tk.Canvas(
            canvas_frame,
            bg='white',
            highlightthickness=1,
            highlightbackground='#ddd'
        )
        self.calendar_canvas.pack(fill=tk.BOTH, expand=True)

        # Bind resize event
        self.calendar_canvas.bind('<Configure>', self._on_canvas_resize)

    def _draw_calendar(self) -> None:
        """Draw the calendar grid and shifts."""
        self.calendar_canvas.delete('all')

        # Get canvas dimensions
        width = self.calendar_canvas.winfo_width()
        height = self.calendar_canvas.winfo_height()

        if width < 100 or height < 100:
            return

        # Layout constants
        time_col_width = 60
        header_height = 40
        available_width = width - time_col_width - 20
        available_height = height - header_height - 20
        day_width = available_width / 7
        hour_height = available_height / len(self.HOURS)

        # Draw header (days)
        for i, day in enumerate(self.DAY_ABBREV):
            x = time_col_width + i * day_width + day_width / 2
            self.calendar_canvas.create_text(
                x, header_height / 2,
                text=day,
                font=('Segoe UI', 11, 'bold'),
                fill='#333'
            )

        # Draw time labels
        for i, hour in enumerate(self.HOURS):
            y = header_height + i * hour_height + hour_height / 2
            self.calendar_canvas.create_text(
                time_col_width / 2, y,
                text=f"{hour}:00",
                font=('Segoe UI', 9),
                fill='#666'
            )

        # Draw grid lines
        for i in range(8):  # Vertical lines
            x = time_col_width + i * day_width
            self.calendar_canvas.create_line(
                x, header_height, x, height - 10,
                fill='#e0e0e0'
            )

        for i in range(len(self.HOURS) + 1):  # Horizontal lines
            y = header_height + i * hour_height
            self.calendar_canvas.create_line(
                time_col_width, y, width - 10, y,
                fill='#e0e0e0'
            )

        # Draw shifts
        for shift in self.shifts:
            self._draw_shift(
                shift,
                time_col_width,
                header_height,
                day_width,
                hour_height
            )

    def _draw_shift(
        self,
        shift: Shift,
        time_col_width: float,
        header_height: float,
        day_width: float,
        hour_height: float
    ) -> None:
        """Draw a single shift on the calendar."""
        # Calculate position
        x1 = time_col_width + shift.day * day_width + 2
        x2 = x1 + day_width - 4
        y1 = header_height + (shift.start_hour - self.HOURS[0]) * hour_height + 2
        y2 = header_height + (shift.end_hour - self.HOURS[0]) * hour_height - 2

        # Determine color
        if shift.shift_type == ShiftType.FIXED:
            color = '#FF9AA2'  # Pink for fixed
            border_color = '#FF6B6B'
        else:
            color = '#B5EAD7'  # Green for flexible
            border_color = '#7BC9A6'

        # Draw rectangle with rounded corners effect
        self.calendar_canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=color,
            outline=border_color,
            width=2
        )

        # Shift name and type indicator
        type_indicator = "📌" if shift.shift_type == ShiftType.FIXED else "🔄"
        title = f"{type_indicator} {shift.name}"

        # Draw title
        self.calendar_canvas.create_text(
            (x1 + x2) / 2, y1 + 12,
            text=title,
            font=('Segoe UI', 9, 'bold'),
            fill='#333',
            width=day_width - 10
        )

        # Draw time
        time_str = f"{shift.start_hour}:00-{shift.end_hour}:00"
        self.calendar_canvas.create_text(
            (x1 + x2) / 2, y1 + 28,
            text=time_str,
            font=('Segoe UI', 8),
            fill='#666'
        )

        # Draw assigned users
        if shift.assigned_users:
            assigned_text = ", ".join(shift.assigned_users)
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 44,
                text=assigned_text,
                font=('Segoe UI', 8, 'italic'),
                fill='#444',
                width=day_width - 10
            )
        else:
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 44,
                text="(unassigned)",
                font=('Segoe UI', 8, 'italic'),
                fill='#999'
            )

    def _on_canvas_resize(self, event) -> None:
        """Handle canvas resize event."""
        self._draw_calendar()

    def _refresh_all(self) -> None:
        """Refresh all UI elements."""
        self._refresh_users_list()
        self._refresh_shifts_list()
        self._draw_calendar()

    def _refresh_users_list(self) -> None:
        """Refresh the users listbox."""
        self.users_listbox.delete(0, tk.END)
        for name, user in sorted(self.users.items()):
            display = f"  {name} (max: {user.max_shifts_per_week} shifts)"
            self.users_listbox.insert(tk.END, display)

    def _refresh_shifts_list(self) -> None:
        """Refresh the shifts listbox."""
        self.shifts_listbox.delete(0, tk.END)
        for shift in self.shifts:
            type_icon = "📌" if shift.shift_type == ShiftType.FIXED else "🔄"
            day_abbrev = self.DAY_ABBREV[shift.day]
            display = (
                f"{type_icon} {shift.name} - "
                f"{day_abbrev} {shift.start_hour}:00-{shift.end_hour}:00"
            )
            self.shifts_listbox.insert(tk.END, display)

    def _on_user_select(self, event) -> None:
        """Handle user selection in listbox."""
        selection = self.users_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_user = list(sorted(self.users.keys()))[index]

    # ========================================================================
    # User Management
    # ========================================================================

    def _add_user(self) -> None:
        """Open dialog to add a new user."""
        dialog = UserDialog(self.root, "Add User", self.USER_COLORS)
        if dialog.result:
            name = dialog.result['name']
            if name in self.users:
                messagebox.showerror("Error", f"User '{name}' already exists!")
                return
            self.users[name] = User(
                name=name,
                max_shifts_per_week=dialog.result['max_shifts'],
                availability=dialog.result['availability'],
                color=dialog.result['color']
            )
            self._save_all()
            self._refresh_all()

    def _edit_user(self) -> None:
        """Open dialog to edit selected user."""
        selection = self.users_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a user to edit.")
            return

        index = selection[0]
        name = list(sorted(self.users.keys()))[index]
        user = self.users[name]

        dialog = UserDialog(
            self.root,
            "Edit User",
            self.USER_COLORS,
            user
        )
        if dialog.result:
            # Update user (name change requires special handling)
            new_name = dialog.result['name']
            if new_name != name:
                if new_name in self.users:
                    messagebox.showerror("Error", f"User '{new_name}' already exists!")
                    return
                del self.users[name]
                # Update conflicts
                new_conflicts = []
                for c1, c2 in self.conflicts:
                    if c1 == name:
                        c1 = new_name
                    if c2 == name:
                        c2 = new_name
                    new_conflicts.append((c1, c2))
                self.conflicts = new_conflicts
                # Update shift assignments
                for shift in self.shifts:
                    if name in shift.assigned_users:
                        shift.assigned_users.remove(name)
                        shift.assigned_users.append(new_name)

            self.users[new_name] = User(
                name=new_name,
                max_shifts_per_week=dialog.result['max_shifts'],
                availability=dialog.result['availability'],
                color=dialog.result['color']
            )
            self._save_all()
            self._refresh_all()

    def _delete_user(self) -> None:
        """Delete selected user."""
        selection = self.users_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a user to delete.")
            return

        index = selection[0]
        name = list(sorted(self.users.keys()))[index]

        if messagebox.askyesno("Confirm Delete", f"Delete user '{name}'?"):
            del self.users[name]
            # Remove from conflicts
            self.conflicts = [
                (c1, c2) for c1, c2 in self.conflicts
                if c1 != name and c2 != name
            ]
            # Remove from shift assignments
            for shift in self.shifts:
                if name in shift.assigned_users:
                    shift.assigned_users.remove(name)
            self._save_all()
            self._refresh_all()

    def _manage_conflicts(self) -> None:
        """Open dialog to manage conflict pairs."""
        dialog = ConflictDialog(self.root, self.users, self.conflicts)
        if dialog.result is not None:
            self.conflicts = dialog.result
            self._save_all()

    # ========================================================================
    # Shift Management
    # ========================================================================

    def _add_shift(self) -> None:
        """Open dialog to add a new shift."""
        dialog = ShiftDialog(self.root, "Add Shift", self.users)
        if dialog.result:
            self.shift_counter += 1
            shift = Shift(
                id=f"shift_{self.shift_counter}",
                name=dialog.result['name'],
                shift_type=dialog.result['shift_type'],
                day=dialog.result['day'],
                start_hour=dialog.result['start_hour'],
                end_hour=dialog.result['end_hour'],
                required_staff=dialog.result['required_staff']
            )
            self.shifts.append(shift)
            self._save_all()
            self._refresh_all()

    def _edit_shift(self) -> None:
        """Open dialog to edit selected shift."""
        selection = self.shifts_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a shift to edit.")
            return

        index = selection[0]
        shift = self.shifts[index]

        dialog = ShiftDialog(self.root, "Edit Shift", self.users, shift)
        if dialog.result:
            shift.name = dialog.result['name']
            shift.shift_type = dialog.result['shift_type']
            shift.day = dialog.result['day']
            shift.start_hour = dialog.result['start_hour']
            shift.end_hour = dialog.result['end_hour']
            shift.required_staff = dialog.result['required_staff']
            self._save_all()
            self._refresh_all()

    def _delete_shift(self) -> None:
        """Delete selected shift."""
        selection = self.shifts_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a shift to delete.")
            return

        index = selection[0]
        shift = self.shifts[index]

        if messagebox.askyesno("Confirm Delete", f"Delete shift '{shift.name}'?"):
            self.shifts.pop(index)
            self._save_all()
            self._refresh_all()

    # ========================================================================
    # Scheduling
    # ========================================================================

    def _auto_schedule(self) -> None:
        """Run automatic scheduling."""
        if not self.users:
            messagebox.showwarning("Warning", "No users to schedule!")
            return
        if not self.shifts:
            messagebox.showwarning("Warning", "No shifts to schedule!")
            return

        scheduler = Scheduler(self.users, self.conflicts)
        self.shifts = scheduler.schedule_shifts(self.shifts)
        self._save_all()
        self._refresh_all()
        messagebox.showinfo("Success", "Auto-scheduling complete!")

    def _clear_assignments(self) -> None:
        """Clear all shift assignments."""
        if messagebox.askyesno("Confirm", "Clear all shift assignments?"):
            for shift in self.shifts:
                shift.assigned_users = []
            self._save_all()
            self._refresh_all()

    # ========================================================================
    # File Operations
    # ========================================================================

    def _save_all(self) -> None:
        """Save all data to files."""
        self.data_manager.save_users(self.users)
        self.data_manager.save_shifts(self.shifts)
        self.data_manager.save_conflicts(self.conflicts)

    def _load_sample_data(self) -> None:
        """Load sample data for demonstration."""
        if self.users or self.shifts:
            if not messagebox.askyesno(
                "Confirm",
                "This will replace existing data. Continue?"
            ):
                return

        # Sample users
        self.users = {
            'Alice': User(
                name='Alice',
                max_shifts_per_week=4,
                color='#FF6B6B'
            ),
            'Bob': User(
                name='Bob',
                max_shifts_per_week=5,
                color='#4ECDC4'
            ),
            'Charlie': User(
                name='Charlie',
                max_shifts_per_week=3,
                color='#45B7D1'
            ),
            'Diana': User(
                name='Diana',
                max_shifts_per_week=4,
                color='#96CEB4'
            ),
            'Eve': User(
                name='Eve',
                max_shifts_per_week=5,
                color='#FFEAA7'
            ),
        }

        # Set some unavailability
        self.users['Alice'].availability[0] = []  # Monday unavailable
        self.users['Charlie'].availability[4] = []  # Friday unavailable

        # Sample shifts
        self.shifts = [
            Shift(
                id='shift_1',
                name='Morning Reception',
                shift_type=ShiftType.FIXED,
                day=0,
                start_hour=9,
                end_hour=12,
                required_staff=2
            ),
            Shift(
                id='shift_2',
                name='Afternoon Support',
                shift_type=ShiftType.FIXED,
                day=0,
                start_hour=13,
                end_hour=17,
                required_staff=2
            ),
            Shift(
                id='shift_3',
                name='Team Meeting',
                shift_type=ShiftType.FLEXIBLE,
                day=2,
                start_hour=10,
                end_hour=12,
                required_staff=3
            ),
            Shift(
                id='shift_4',
                name='Training Session',
                shift_type=ShiftType.FLEXIBLE,
                day=3,
                start_hour=14,
                end_hour=16,
                required_staff=2
            ),
            Shift(
                id='shift_5',
                name='Weekly Review',
                shift_type=ShiftType.FIXED,
                day=4,
                start_hour=15,
                end_hour=17,
                required_staff=2
            ),
        ]
        self.shift_counter = 5

        # Sample conflicts
        self.conflicts = [('Alice', 'Bob')]

        self._save_all()
        self._refresh_all()
        messagebox.showinfo("Success", "Sample data loaded!")

    def _show_about(self) -> None:
        """Show about dialog."""
        messagebox.showinfo(
            "About AutoSchedule",
            "AutoSchedule v1.0\n\n"
            "Automatic Shift Scheduling Application\n\n"
            "Features:\n"
            "• User profile management\n"
            "• Fixed and flexible shift types\n"
            "• 7-day availability settings\n"
            "• Conflict pair management\n"
            "• Automatic scheduling algorithm\n\n"
            "© 2026 AutoSchedule"
        )


# ============================================================================
# DIALOGS
# ============================================================================

class UserDialog:
    """Dialog for adding/editing users."""

    DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    HOURS = list(range(8, 19))

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        colors: List[str],
        user: User = None
    ):
        """Initialize user dialog."""
        self.result = None
        self.colors = colors
        self.user = user

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("700x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()

        # Wait for dialog to close
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Name and max shifts row
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(info_frame, text="Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(
            value=self.user.name if self.user else ""
        )
        name_entry = ttk.Entry(info_frame, textvariable=self.name_var, width=20)
        name_entry.pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(info_frame, text="Max Shifts/Week:").pack(side=tk.LEFT)
        self.max_shifts_var = tk.IntVar(
            value=self.user.max_shifts_per_week if self.user else 5
        )
        max_shifts_spin = ttk.Spinbox(
            info_frame,
            from_=1,
            to=14,
            textvariable=self.max_shifts_var,
            width=5
        )
        max_shifts_spin.pack(side=tk.LEFT, padx=5)

        ttk.Label(info_frame, text="Color:").pack(side=tk.LEFT, padx=(20, 5))
        self.color_var = tk.StringVar(
            value=self.user.color if self.user else self.colors[0]
        )
        color_combo = ttk.Combobox(
            info_frame,
            textvariable=self.color_var,
            values=self.colors,
            width=10,
            state='readonly'
        )
        color_combo.pack(side=tk.LEFT)

        # Availability section
        ttk.Label(
            main_frame,
            text="Availability (click cells to toggle):",
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor=tk.W, pady=(0, 5))

        # Create availability grid
        grid_frame = ttk.Frame(main_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        # Store checkbuttons
        self.availability_vars: Dict[int, Dict[int, tk.BooleanVar]] = {}

        # Header row (hours)
        ttk.Label(grid_frame, text="", width=5).grid(row=0, column=0)
        for i, hour in enumerate(self.HOURS):
            ttk.Label(
                grid_frame,
                text=f"{hour}",
                width=3,
                font=('Segoe UI', 8)
            ).grid(row=0, column=i + 1)

        # Day rows
        for day_idx, day_name in enumerate(self.DAYS):
            ttk.Label(
                grid_frame,
                text=day_name,
                width=5,
                font=('Segoe UI', 9, 'bold')
            ).grid(row=day_idx + 1, column=0, sticky=tk.W)

            self.availability_vars[day_idx] = {}
            for hour_idx, hour in enumerate(self.HOURS):
                # Default availability
                if self.user:
                    is_available = hour in self.user.availability.get(day_idx, [])
                else:
                    is_available = True

                var = tk.BooleanVar(value=is_available)
                self.availability_vars[day_idx][hour] = var

                cb = tk.Checkbutton(
                    grid_frame,
                    variable=var,
                    bg='#90EE90' if is_available else '#FFB6C1',
                    activebackground='#90EE90',
                    selectcolor='#90EE90',
                    indicatoron=False,
                    width=2,
                    height=1
                )
                cb.grid(row=day_idx + 1, column=hour_idx + 1, padx=1, pady=1)

                # Update color on click
                def update_color(cb=cb, var=var):
                    cb.configure(bg='#90EE90' if var.get() else '#FFB6C1')
                var.trace_add('write', lambda *args, cb=cb, var=var: update_color(cb, var))

        # Quick actions
        quick_frame = ttk.Frame(main_frame)
        quick_frame.pack(fill=tk.X, pady=10)

        ttk.Button(
            quick_frame,
            text="Select All",
            command=self._select_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            quick_frame,
            text="Clear All",
            command=self._clear_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            quick_frame,
            text="Weekdays Only",
            command=self._weekdays_only
        ).pack(side=tk.LEFT, padx=5)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame,
            text="Save",
            command=self._save
        ).pack(side=tk.RIGHT, padx=5)

    def _select_all(self) -> None:
        """Select all availability."""
        for day_vars in self.availability_vars.values():
            for var in day_vars.values():
                var.set(True)

    def _clear_all(self) -> None:
        """Clear all availability."""
        for day_vars in self.availability_vars.values():
            for var in day_vars.values():
                var.set(False)

    def _weekdays_only(self) -> None:
        """Set availability to weekdays only."""
        for day_idx, day_vars in self.availability_vars.items():
            for var in day_vars.values():
                var.set(day_idx < 5)

    def _save(self) -> None:
        """Save and close dialog."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required!")
            return

        # Build availability dict
        availability = {}
        for day_idx, day_vars in self.availability_vars.items():
            available_hours = [
                hour for hour, var in day_vars.items() if var.get()
            ]
            availability[day_idx] = available_hours

        self.result = {
            'name': name,
            'max_shifts': self.max_shifts_var.get(),
            'availability': availability,
            'color': self.color_var.get()
        }
        self.dialog.destroy()


class ShiftDialog:
    """Dialog for adding/editing shifts."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        users: Dict[str, User],
        shift: Shift = None
    ):
        """Initialize shift dialog."""
        self.result = None
        self.users = users
        self.shift = shift

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x350")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 350) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()

        # Wait for dialog to close
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Name
        ttk.Label(main_frame, text="Shift Name:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.name_var = tk.StringVar(
            value=self.shift.name if self.shift else ""
        )
        ttk.Entry(main_frame, textvariable=self.name_var, width=30).grid(
            row=0, column=1, columnspan=2, sticky=tk.W, pady=5
        )

        # Shift Type
        ttk.Label(main_frame, text="Shift Type:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.type_var = tk.StringVar(
            value=self.shift.shift_type.value if self.shift else "fixed"
        )
        type_frame = ttk.Frame(main_frame)
        type_frame.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=5)

        ttk.Radiobutton(
            type_frame,
            text="📌 Fixed (time-sensitive)",
            variable=self.type_var,
            value="fixed"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            type_frame,
            text="🔄 Flexible (auto-adjust)",
            variable=self.type_var,
            value="flexible"
        ).pack(side=tk.LEFT, padx=(15, 0))

        # Day
        ttk.Label(main_frame, text="Day:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.day_var = tk.StringVar(
            value=self.DAYS[self.shift.day] if self.shift else self.DAYS[0]
        )
        day_combo = ttk.Combobox(
            main_frame,
            textvariable=self.day_var,
            values=self.DAYS,
            state='readonly',
            width=15
        )
        day_combo.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=5)

        # Start Time
        ttk.Label(main_frame, text="Start Time:").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        self.start_var = tk.IntVar(
            value=self.shift.start_hour if self.shift else 9
        )
        start_spin = ttk.Spinbox(
            main_frame,
            from_=8,
            to=17,
            textvariable=self.start_var,
            width=5,
            format="%02.0f"
        )
        start_spin.grid(row=3, column=1, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text=":00").grid(row=3, column=2, sticky=tk.W)

        # End Time
        ttk.Label(main_frame, text="End Time:").grid(
            row=4, column=0, sticky=tk.W, pady=5
        )
        self.end_var = tk.IntVar(
            value=self.shift.end_hour if self.shift else 17
        )
        end_spin = ttk.Spinbox(
            main_frame,
            from_=9,
            to=18,
            textvariable=self.end_var,
            width=5,
            format="%02.0f"
        )
        end_spin.grid(row=4, column=1, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text=":00").grid(row=4, column=2, sticky=tk.W)

        # Required Staff
        ttk.Label(main_frame, text="Required Staff:").grid(
            row=5, column=0, sticky=tk.W, pady=5
        )
        self.staff_var = tk.IntVar(
            value=self.shift.required_staff if self.shift else 1
        )
        staff_spin = ttk.Spinbox(
            main_frame,
            from_=1,
            to=10,
            textvariable=self.staff_var,
            width=5
        )
        staff_spin.grid(row=5, column=1, sticky=tk.W, pady=5)

        # Note for flexible shifts
        note_label = ttk.Label(
            main_frame,
            text="Note: Flexible shifts may be moved to optimal\n"
                 "times during auto-scheduling.",
            font=('Segoe UI', 9, 'italic'),
            foreground='#666'
        )
        note_label.grid(row=6, column=0, columnspan=3, pady=15)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(10, 0))

        ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame,
            text="Save",
            command=self._save
        ).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        """Save and close dialog."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Shift name is required!")
            return

        start = self.start_var.get()
        end = self.end_var.get()
        if end <= start:
            messagebox.showerror("Error", "End time must be after start time!")
            return

        self.result = {
            'name': name,
            'shift_type': ShiftType(self.type_var.get()),
            'day': self.DAYS.index(self.day_var.get()),
            'start_hour': start,
            'end_hour': end,
            'required_staff': self.staff_var.get()
        }
        self.dialog.destroy()


class ConflictDialog:
    """Dialog for managing conflict pairs."""

    def __init__(
        self,
        parent: tk.Tk,
        users: Dict[str, User],
        conflicts: List[Tuple[str, str]]
    ):
        """Initialize conflict dialog."""
        self.result = None
        self.users = users
        self.conflicts = list(conflicts)

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Manage Conflict Pairs")
        self.dialog.geometry("450x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()

        # Wait for dialog to close
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text="Users in conflict pairs cannot be scheduled together.",
            font=('Segoe UI', 9, 'italic'),
            foreground='#666'
        ).pack(anchor=tk.W, pady=(0, 10))

        # Add conflict frame
        add_frame = ttk.LabelFrame(main_frame, text="Add Conflict Pair", padding=10)
        add_frame.pack(fill=tk.X, pady=(0, 10))

        user_names = list(sorted(self.users.keys()))

        ttk.Label(add_frame, text="User 1:").grid(row=0, column=0, padx=5)
        self.user1_var = tk.StringVar()
        user1_combo = ttk.Combobox(
            add_frame,
            textvariable=self.user1_var,
            values=user_names,
            state='readonly',
            width=15
        )
        user1_combo.grid(row=0, column=1, padx=5)

        ttk.Label(add_frame, text="User 2:").grid(row=0, column=2, padx=5)
        self.user2_var = tk.StringVar()
        user2_combo = ttk.Combobox(
            add_frame,
            textvariable=self.user2_var,
            values=user_names,
            state='readonly',
            width=15
        )
        user2_combo.grid(row=0, column=3, padx=5)

        ttk.Button(
            add_frame,
            text="Add",
            command=self._add_conflict
        ).grid(row=0, column=4, padx=10)

        # Existing conflicts listbox
        ttk.Label(main_frame, text="Existing Conflicts:").pack(anchor=tk.W)

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.conflicts_listbox = tk.Listbox(
            list_frame,
            font=('Segoe UI', 10)
        )
        self.conflicts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient=tk.VERTICAL,
            command=self.conflicts_listbox.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conflicts_listbox.config(yscrollcommand=scrollbar.set)

        self._refresh_list()

        # Remove button
        ttk.Button(
            main_frame,
            text="Remove Selected",
            command=self._remove_conflict
        ).pack(anchor=tk.W, pady=5)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame,
            text="Save",
            command=self._save
        ).pack(side=tk.RIGHT, padx=5)

    def _refresh_list(self) -> None:
        """Refresh conflicts listbox."""
        self.conflicts_listbox.delete(0, tk.END)
        for user1, user2 in self.conflicts:
            self.conflicts_listbox.insert(tk.END, f"  {user1}  ↔  {user2}")

    def _add_conflict(self) -> None:
        """Add a new conflict pair."""
        user1 = self.user1_var.get()
        user2 = self.user2_var.get()

        if not user1 or not user2:
            messagebox.showerror("Error", "Please select both users!")
            return

        if user1 == user2:
            messagebox.showerror("Error", "Cannot conflict with self!")
            return

        # Check if already exists
        for c1, c2 in self.conflicts:
            if (c1 == user1 and c2 == user2) or (c1 == user2 and c2 == user1):
                messagebox.showwarning("Warning", "Conflict pair already exists!")
                return

        self.conflicts.append((user1, user2))
        self._refresh_list()

    def _remove_conflict(self) -> None:
        """Remove selected conflict pair."""
        selection = self.conflicts_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a conflict to remove.")
            return

        index = selection[0]
        self.conflicts.pop(index)
        self._refresh_list()

    def _save(self) -> None:
        """Save and close dialog."""
        self.result = self.conflicts
        self.dialog.destroy()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Application entry point."""
    root = tk.Tk()
    app = SchedulerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
