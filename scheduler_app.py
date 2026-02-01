"""
AutoSchedule - Automatic Shift Scheduling Application
A GUI application for managing user profiles, shifts, and automatic scheduling.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from datetime import datetime
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
class TimeRange:
    """Represents a time range within a day."""
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int

    def to_minutes(self) -> Tuple[int, int]:
        """Convert to start/end in minutes from midnight."""
        start = self.start_hour * 60 + self.start_minute
        end = self.end_hour * 60 + self.end_minute
        return start, end

    def overlaps(self, other: 'TimeRange') -> bool:
        """Check if this time range overlaps with another."""
        s1, e1 = self.to_minutes()
        s2, e2 = other.to_minutes()
        return s1 < e2 and s2 < e1

    def contains_time(self, hour: int, minute: int) -> bool:
        """Check if a specific time is within this range."""
        time_mins = hour * 60 + minute
        start, end = self.to_minutes()
        return start <= time_mins < end

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'start_hour': self.start_hour,
            'start_minute': self.start_minute,
            'end_hour': self.end_hour,
            'end_minute': self.end_minute
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TimeRange':
        """Create from dictionary."""
        return cls(
            start_hour=data['start_hour'],
            start_minute=data['start_minute'],
            end_hour=data['end_hour'],
            end_minute=data['end_minute']
        )

    def __str__(self) -> str:
        """String representation."""
        return (
            f"{self.start_hour:02d}:{self.start_minute:02d} - "
            f"{self.end_hour:02d}:{self.end_minute:02d}"
        )


@dataclass
class User:
    """Represents a user/employee with availability settings."""
    name: str
    max_shifts_per_week: int = 5
    # Availability: dict mapping day (0-6) to list of TimeRange objects
    availability: Dict[int, List[TimeRange]] = field(default_factory=dict)
    color: str = "#4A90D9"

    def __post_init__(self):
        """Initialize default availability (all day available)."""
        if not self.availability:
            for day in range(7):
                # Default: available all day
                self.availability[day] = [TimeRange(0, 0, 24, 0)]

    def is_available(self, day: int, start_hour: int, start_minute: int,
                     end_hour: int, end_minute: int) -> bool:
        """Check if user is available for a time range on a day."""
        day_key = int(day)
        if day_key not in self.availability:
            return False

        if not self.availability.get(day_key):
            return False

        check_start = start_hour * 60 + start_minute
        check_end = end_hour * 60 + end_minute

        # Check if the entire requested range is covered by availability
        for time_range in self.availability.get(day_key, []):
            avail_start, avail_end = time_range.to_minutes()
            if avail_start <= check_start and avail_end >= check_end:
                return True
        return False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        availability_dict = {}
        for day, ranges in self.availability.items():
            availability_dict[str(day)] = [r.to_dict() for r in ranges]
        return {
            'name': self.name,
            'max_shifts_per_week': self.max_shifts_per_week,
            'availability': availability_dict,
            'color': self.color
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create User from dictionary."""
        availability = {}
        for day_str, ranges in data.get('availability', {}).items():
            day = int(day_str)
            # Handle both new format (list of TimeRange dicts) and
            # old format (list of integers representing hours)
            time_ranges = []
            for item in ranges:
                if isinstance(item, dict):
                    # New format: TimeRange dictionary
                    time_ranges.append(TimeRange.from_dict(item))
                elif isinstance(item, int):
                    # Old format: integer hour - convert to hour block
                    time_ranges.append(TimeRange(item, 0, item + 1, 0))
            # Merge consecutive hour blocks from old format
            if time_ranges and all(
                tr.start_minute == 0 and tr.end_minute == 0 and
                tr.end_hour - tr.start_hour == 1
                for tr in time_ranges
            ):
                time_ranges = cls._merge_hour_blocks(time_ranges)
            availability[day] = time_ranges
        return cls(
            name=data['name'],
            max_shifts_per_week=data.get('max_shifts_per_week', 5),
            availability=availability,
            color=data.get('color', '#4A90D9')
        )

    @staticmethod
    def _merge_hour_blocks(hour_blocks: List['TimeRange']) -> List['TimeRange']:
        """Merge consecutive hour blocks into continuous ranges."""
        if not hour_blocks:
            return []
        # Sort by start hour
        sorted_blocks = sorted(hour_blocks, key=lambda tr: tr.start_hour)
        merged = []
        current_start = sorted_blocks[0].start_hour
        current_end = sorted_blocks[0].end_hour

        for block in sorted_blocks[1:]:
            if block.start_hour == current_end:
                # Consecutive, extend
                current_end = block.end_hour
            else:
                # Gap, save current and start new
                merged.append(TimeRange(current_start, 0, current_end, 0))
                current_start = block.start_hour
                current_end = block.end_hour

        merged.append(TimeRange(current_start, 0, current_end, 0))
        return merged


@dataclass
class Shift:
    """Represents a shift that needs to be staffed."""
    id: str
    name: str
    shift_type: ShiftType
    day: int  # 0=Monday, 6=Sunday
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    required_staff: int = 2
    assigned_users: List[str] = field(default_factory=list)

    def duration_minutes(self) -> int:
        """Return shift duration in minutes."""
        start = self.start_hour * 60 + self.start_minute
        end = self.end_hour * 60 + self.end_minute
        return end - start

    def to_time_range(self) -> TimeRange:
        """Convert shift times to TimeRange."""
        return TimeRange(
            self.start_hour, self.start_minute,
            self.end_hour, self.end_minute
        )

    def overlaps_with(self, other: 'Shift') -> bool:
        """Check if this shift overlaps with another on the same day."""
        if self.day != other.day:
            return False
        return self.to_time_range().overlaps(other.to_time_range())

    def time_str(self) -> str:
        """Return formatted time string."""
        return (
            f"{self.start_hour:02d}:{self.start_minute:02d}-"
            f"{self.end_hour:02d}:{self.end_minute:02d}"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'shift_type': self.shift_type.value,
            'day': self.day,
            'start_hour': self.start_hour,
            'start_minute': self.start_minute,
            'end_hour': self.end_hour,
            'end_minute': self.end_minute,
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
            start_minute=data.get('start_minute', 0),
            end_hour=data['end_hour'],
            end_minute=data.get('end_minute', 0),
            required_staff=data.get('required_staff', 2),
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
        self.settings_file = os.path.join(data_dir, 'settings.json')

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
            return {name: User.from_dict(ud) for name, ud in data.items()}
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

    def save_settings(self, settings: dict) -> None:
        """Save application settings."""
        with open(self.settings_file, 'w') as f:
            json.dump(settings, f, indent=2)

    def load_settings(self) -> dict:
        """Load application settings."""
        if not os.path.exists(self.settings_file):
            return {'dark_mode': False}
        try:
            with open(self.settings_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return {'dark_mode': False}


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

    def check_user_overlap(
        self,
        user_name: str,
        shift: Shift,
        all_shifts: List[Shift]
    ) -> bool:
        """Check if assigning user to shift would cause overlap."""
        for other_shift in all_shifts:
            if other_shift.id == shift.id:
                continue
            if user_name in other_shift.assigned_users:
                if shift.overlaps_with(other_shift):
                    return True
        return False

    def get_available_users(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int],
        all_shifts: List[Shift]
    ) -> List[str]:
        """Get list of users available for a shift."""
        candidates = []
        for name, user in self.users.items():
            # Check max shifts
            if shifts_worked.get(name, 0) >= user.max_shifts_per_week:
                continue
            # Check availability
            if not user.is_available(
                shift.day,
                shift.start_hour, shift.start_minute,
                shift.end_hour, shift.end_minute
            ):
                continue
            # Check for overlapping shifts
            if self.check_user_overlap(name, shift, all_shifts):
                continue
            candidates.append(name)
        return candidates

    def schedule_shifts(self, shifts: List[Shift]) -> List[Shift]:
        """
        Automatically assign users to shifts with load balancing.
        Fixed shifts are scheduled first, then flexible shifts.
        Prioritizes equitable distribution of shifts among users.
        """
        # Work with copies to avoid modifying originals
        scheduled_shifts = [copy.deepcopy(s) for s in shifts]

        # Track shifts worked per user
        shifts_worked = {name: 0 for name in self.users}

        # Count already assigned shifts
        for shift in scheduled_shifts:
            for user in shift.assigned_users:
                if user in shifts_worked:
                    shifts_worked[user] += 1

        # Separate fixed and flexible shifts
        fixed_shifts = [
            s for s in scheduled_shifts if s.shift_type == ShiftType.FIXED
        ]
        flexible_shifts = [
            s for s in scheduled_shifts if s.shift_type == ShiftType.FLEXIBLE
        ]

        # Schedule fixed shifts first (they can't be moved)
        for shift in fixed_shifts:
            self._assign_shift_balanced(shift, shifts_worked, scheduled_shifts)

        # Schedule flexible shifts (can move to optimal timing)
        for shift in flexible_shifts:
            best_slot = self._find_best_slot(shift, shifts_worked, scheduled_shifts)
            if best_slot:
                shift.day = best_slot[0]
                shift.start_hour = best_slot[1]
                shift.start_minute = best_slot[2]
                shift.end_hour = best_slot[3]
                shift.end_minute = best_slot[4]
            self._assign_shift_balanced(shift, shifts_worked, scheduled_shifts)

        return scheduled_shifts

    def _assign_shift_balanced(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int],
        all_shifts: List[Shift]
    ) -> None:
        """
        Assign users to a single shift with load balancing.
        Prioritizes users with fewer shifts to achieve equitable distribution.
        """
        # Keep existing assignments only if they respect all constraints
        # (existence, no overlap, availability/max_shifts, and no conflicts).
        available_users = set(self.get_available_users(shift, shifts_worked, all_shifts))
        valid_assigned = []
        for user in shift.assigned_users:
            if user not in self.users:
                continue
            # Verify user doesn't have overlapping shift already
            if self.check_user_overlap(user, shift, all_shifts):
                continue
            # Verify user is otherwise available (availability windows, max shifts, etc.)
            if user not in available_users:
                continue
            # Ensure no conflict with already-preserved users on this shift
            if self.has_conflict(valid_assigned, user):
                continue
            valid_assigned.append(user)

        shift.assigned_users = valid_assigned

        # Get candidates for remaining spots
        needed = shift.required_staff - len(shift.assigned_users)
        if needed <= 0:
            return

        candidates = self.get_available_users(shift, shifts_worked, all_shifts)

        # Remove already assigned users
        candidates = [c for c in candidates if c not in shift.assigned_users]

        # Calculate target shifts per user for load balancing
        total_slots_needed = sum(s.required_staff for s in all_shifts)
        num_users = len(self.users) if self.users else 1
        target_per_user = total_slots_needed / num_users

        # Score candidates: prioritize those furthest below target
        def balance_score(user: str) -> float:
            current = shifts_worked.get(user, 0)
            max_allowed = self.users[user].max_shifts_per_week
            # Primary: how far below target (higher = more priority)
            below_target = target_per_user - current
            # Secondary: capacity remaining
            capacity = max_allowed - current
            # Tertiary: small random factor for tie-breaking
            random_factor = random.random() * 0.1
            return (below_target * 10) + capacity + random_factor

        # Sort by balance score (highest first = most need for shifts)
        candidates.sort(key=balance_score, reverse=True)

        for candidate in candidates:
            if len(shift.assigned_users) >= shift.required_staff:
                break
            if not self.has_conflict(shift.assigned_users, candidate):
                shift.assigned_users.append(candidate)
                shifts_worked[candidate] = shifts_worked.get(candidate, 0) + 1

    def _find_best_slot(
        self,
        shift: Shift,
        shifts_worked: Dict[str, int],
        all_shifts: List[Shift]
    ) -> Optional[Tuple[int, int, int, int, int]]:
        """
        Find the best time slot for a flexible shift.
        Returns (day, start_hour, start_min, end_hour, end_min) or None.
        """
        duration = shift.duration_minutes()
        best_slot = None
        best_score = -1

        # Try each day and hour
        for day in range(7):
            for start_hour in range(24):
                for start_minute in [0, 30]:  # Try on the hour and half hour
                    end_minutes = start_hour * 60 + start_minute + duration
                    if end_minutes > 24 * 60:
                        continue
                    end_hour = end_minutes // 60
                    end_minute = end_minutes % 60

                    # Create test shift
                    test_shift = copy.deepcopy(shift)
                    test_shift.day = day
                    test_shift.start_hour = start_hour
                    test_shift.start_minute = start_minute
                    test_shift.end_hour = end_hour
                    test_shift.end_minute = end_minute

                    # Check for overlap with other shifts
                    has_overlap = False
                    for other in all_shifts:
                        if other.id != shift.id and test_shift.overlaps_with(other):
                            has_overlap = True
                            break

                    if has_overlap:
                        continue

                    # Count available users for this slot
                    available_count = 0
                    for name, user in self.users.items():
                        if shifts_worked.get(name, 0) >= user.max_shifts_per_week:
                            continue
                        if user.is_available(
                            day, start_hour, start_minute, end_hour, end_minute
                        ):
                            available_count += 1

                    # Score based on available users
                    if (available_count >= shift.required_staff and
                            available_count > best_score):
                        best_score = available_count
                        best_slot = (
                            day, start_hour, start_minute, end_hour, end_minute
                        )

        return best_slot


# ============================================================================
# THEME MANAGER
# ============================================================================

class ThemeManager:
    """Manages light and dark themes."""

    LIGHT_THEME = {
        'bg': '#f5f5f5',
        'fg': '#333333',
        'card_bg': '#ffffff',
        'card_border': '#dddddd',
        'accent': '#4A90D9',
        'accent_hover': '#357ABD',
        'listbox_bg': '#ffffff',
        'listbox_fg': '#333333',
        'listbox_select_bg': '#4A90D9',
        'listbox_select_fg': '#ffffff',
        'canvas_bg': '#ffffff',
        'grid_line': '#e0e0e0',
        'shift_fixed': '#FF9AA2',
        'shift_fixed_border': '#FF6B6B',
        'shift_flexible': '#B5EAD7',
        'shift_flexible_border': '#7BC9A6',
        'shift_overlap': '#FFD700',
        'shift_overlap_border': '#FFA500',
        'text_secondary': '#666666',
        'text_muted': '#999999',
        'success': '#28a745',
        'warning': '#ffc107',
        'danger': '#dc3545',
        'button_bg': '#e0e0e0',
        'entry_bg': '#ffffff',
    }

    DARK_THEME = {
        'bg': '#1e1e1e',
        'fg': '#e0e0e0',
        'card_bg': '#2d2d2d',
        'card_border': '#404040',
        'accent': '#5BA0D0',
        'accent_hover': '#4A90D9',
        'listbox_bg': '#2d2d2d',
        'listbox_fg': '#e0e0e0',
        'listbox_select_bg': '#5BA0D0',
        'listbox_select_fg': '#ffffff',
        'canvas_bg': '#2d2d2d',
        'grid_line': '#404040',
        'shift_fixed': '#8B4A50',
        'shift_fixed_border': '#A05A60',
        'shift_flexible': '#4A7A6A',
        'shift_flexible_border': '#5A8A7A',
        'shift_overlap': '#8B7500',
        'shift_overlap_border': '#9B8500',
        'text_secondary': '#aaaaaa',
        'text_muted': '#777777',
        'success': '#3CB371',
        'warning': '#DAA520',
        'danger': '#CD5C5C',
        'button_bg': '#404040',
        'entry_bg': '#3d3d3d',
    }

    def __init__(self, dark_mode: bool = False):
        """Initialize theme manager."""
        self.dark_mode = dark_mode

    @property
    def theme(self) -> dict:
        """Get current theme colors."""
        return self.DARK_THEME if self.dark_mode else self.LIGHT_THEME

    def toggle(self) -> None:
        """Toggle between light and dark mode."""
        self.dark_mode = not self.dark_mode


# ============================================================================
# GUI APPLICATION
# ============================================================================

class SchedulerApp:
    """Main application window."""

    DAYS = [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday',
        'Friday', 'Saturday', 'Sunday'
    ]
    DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    # Color palette for users
    USER_COLORS = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]

    def __init__(self, root: tk.Tk):
        """Initialize the application."""
        self.root = root
        self.root.title("AutoSchedule - Shift Scheduling Application")
        self.root.geometry("1600x950")
        self.root.minsize(1400, 800)

        # Data
        self.data_manager = DataManager()
        self.users: Dict[str, User] = self.data_manager.load_users()
        self.shifts: List[Shift] = self.data_manager.load_shifts()
        self.conflicts: List[Tuple[str, str]] = self.data_manager.load_conflicts()

        # Settings and theme
        self.settings = self.data_manager.load_settings()
        self.theme_manager = ThemeManager(self.settings.get('dark_mode', False))

        # UI State
        self.selected_user: Optional[str] = None
        self.shift_counter = len(self.shifts)

        # Setup UI
        self._create_menu()
        self._create_main_layout()
        self._apply_theme()
        self._refresh_all()

    def _apply_theme(self) -> None:
        """Apply current theme to all widgets."""
        theme = self.theme_manager.theme

        # Configure root
        self.root.configure(bg=theme['bg'])

        # Configure ttk styles
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('TFrame', background=theme['bg'])
        style.configure('TLabel', background=theme['bg'], foreground=theme['fg'])
        style.configure(
            'TButton',
            background=theme['button_bg'],
            foreground=theme['fg']
        )
        style.map(
            'TButton',
            background=[('active', theme['accent_hover'])]
        )
        style.configure(
            'Header.TLabel',
            font=('Segoe UI', 14, 'bold'),
            background=theme['bg'],
            foreground=theme['fg']
        )
        style.configure(
            'Subheader.TLabel',
            font=('Segoe UI', 11, 'bold'),
            background=theme['bg'],
            foreground=theme['fg']
        )
        style.configure(
            'TLabelframe',
            background=theme['bg'],
            foreground=theme['fg']
        )
        style.configure(
            'TLabelframe.Label',
            background=theme['bg'],
            foreground=theme['fg']
        )
        style.configure(
            'Primary.TButton',
            font=('Segoe UI', 10, 'bold'),
            padding=(15, 8)
        )

        # Update listboxes
        if hasattr(self, 'users_listbox'):
            self.users_listbox.configure(
                bg=theme['listbox_bg'],
                fg=theme['listbox_fg'],
                selectbackground=theme['listbox_select_bg'],
                selectforeground=theme['listbox_select_fg'],
                highlightbackground=theme['card_border'],
                highlightcolor=theme['accent']
            )
        if hasattr(self, 'shifts_listbox'):
            self.shifts_listbox.configure(
                bg=theme['listbox_bg'],
                fg=theme['listbox_fg'],
                selectbackground=theme['listbox_select_bg'],
                selectforeground=theme['listbox_select_fg'],
                highlightbackground=theme['card_border'],
                highlightcolor=theme['accent']
            )

        # Update canvas
        if hasattr(self, 'calendar_canvas'):
            self.calendar_canvas.configure(
                bg=theme['canvas_bg'],
                highlightbackground=theme['card_border']
            )

        # Redraw calendar
        if hasattr(self, 'calendar_canvas'):
            self._draw_calendar()

    def _create_menu(self) -> None:
        """Create application menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save All", command=self._save_all)
        file_menu.add_command(
            label="Load Sample Data",
            command=self._load_sample_data
        )
        file_menu.add_separator()
        file_menu.add_command(label="Print Schedule", command=self._print_schedule)
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
        schedule_menu.add_separator()
        schedule_menu.add_command(
            label="Check User Conflicts",
            command=self._check_user_conflicts
        )

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self.dark_mode_var = tk.BooleanVar(value=self.theme_manager.dark_mode)
        view_menu.add_checkbutton(
            label="Dark Mode",
            variable=self.dark_mode_var,
            command=self._toggle_dark_mode
        )

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self) -> None:
        """Create main application layout."""

        # Main container with padding
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel (Users and Shifts)
        left_panel = ttk.Frame(self.main_frame, width=400)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        # Users section
        self._create_users_panel(left_panel)

        # Shifts section
        self._create_shifts_panel(left_panel)

        # Right panel (Calendar)
        right_panel = ttk.Frame(self.main_frame)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_calendar_panel(right_panel)

    def _create_users_panel(self, parent: ttk.Frame) -> None:
        """Create the users management panel."""
        theme = self.theme_manager.theme

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
            bg=theme['listbox_bg'],
            fg=theme['listbox_fg'],
            selectbackground=theme['listbox_select_bg'],
            selectforeground=theme['listbox_select_fg']
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
        theme = self.theme_manager.theme

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
            highlightthickness=1,
            bg=theme['listbox_bg'],
            fg=theme['listbox_fg'],
            selectbackground=theme['listbox_select_bg'],
            selectforeground=theme['listbox_select_fg']
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

        # Manual assign button
        ttk.Button(
            parent,
            text="👥 Assign Users to Shift",
            command=self._manual_assign
        ).pack(fill=tk.X, pady=(0, 5))

        # Auto-schedule button
        ttk.Button(
            parent,
            text="🔄 Auto-Schedule",
            style='Primary.TButton',
            command=self._auto_schedule
        ).pack(fill=tk.X, pady=(5, 0))

    def _create_calendar_panel(self, parent: ttk.Frame) -> None:
        """Create the calendar view panel."""
        theme = self.theme_manager.theme

        # Header with legend
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            header_frame,
            text="📆 Weekly Schedule",
            style='Header.TLabel'
        ).pack(side=tk.LEFT)

        # Legend
        legend_frame = ttk.Frame(header_frame)
        legend_frame.pack(side=tk.RIGHT)

        # Fixed shift legend
        fixed_legend = tk.Canvas(
            legend_frame, width=15, height=15, highlightthickness=0,
            bg=theme['bg']
        )
        fixed_legend.create_rectangle(0, 0, 15, 15, fill=theme['shift_fixed'], outline='')
        fixed_legend.pack(side=tk.LEFT, padx=(10, 2))
        ttk.Label(legend_frame, text="Fixed", font=('Segoe UI', 9)).pack(side=tk.LEFT)

        # Flexible shift legend
        flex_legend = tk.Canvas(
            legend_frame, width=15, height=15, highlightthickness=0,
            bg=theme['bg']
        )
        flex_legend.create_rectangle(0, 0, 15, 15, fill=theme['shift_flexible'], outline='')
        flex_legend.pack(side=tk.LEFT, padx=(10, 2))
        ttk.Label(legend_frame, text="Flexible", font=('Segoe UI', 9)).pack(side=tk.LEFT)



        # Calendar canvas with scrollbars
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        # Vertical scrollbar
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.calendar_canvas = tk.Canvas(
            canvas_frame,
            bg=theme['canvas_bg'],
            highlightthickness=1,
            highlightbackground=theme['card_border'],
            yscrollcommand=v_scroll.set
        )
        self.calendar_canvas.pack(fill=tk.BOTH, expand=True)
        v_scroll.config(command=self.calendar_canvas.yview)

        # Bind resize and scroll events
        self.calendar_canvas.bind('<Configure>', self._on_canvas_resize)
        self.calendar_canvas.bind('<MouseWheel>', self._on_canvas_scroll)

    def _group_overlapping_shifts(self, shifts: List[Shift]) -> List[List[Shift]]:
        """Group shifts that overlap with each other for side-by-side display."""
        if not shifts:
            return []

        # Sort by start time
        sorted_shifts = sorted(
            shifts, key=lambda s: s.start_hour * 60 + s.start_minute
        )

        groups = []
        current_group = [sorted_shifts[0]]
        group_end = sorted_shifts[0].end_hour * 60 + sorted_shifts[0].end_minute

        for shift in sorted_shifts[1:]:
            shift_start = shift.start_hour * 60 + shift.start_minute
            shift_end = shift.end_hour * 60 + shift.end_minute

            # Check if this shift overlaps with current group
            if shift_start < group_end:
                current_group.append(shift)
                group_end = max(group_end, shift_end)
            else:
                groups.append(current_group)
                current_group = [shift]
                group_end = shift_end

        groups.append(current_group)
        return groups

    def _draw_calendar(self) -> None:
        """Draw the calendar grid and shifts."""
        self.calendar_canvas.delete('all')
        theme = self.theme_manager.theme

        # Get canvas dimensions
        width = self.calendar_canvas.winfo_width()
        height = max(self.calendar_canvas.winfo_height(), 800)

        if width < 100:
            return

        # Layout constants
        time_col_width = 60
        header_height = 40
        available_width = width - time_col_width - 30
        day_width = available_width / 7

        # 24 hours display
        hours = list(range(24))
        hour_height = max(30, (height - header_height - 20) / len(hours))
        total_height = header_height + hour_height * len(hours) + 20

        # Configure scroll region
        self.calendar_canvas.configure(scrollregion=(0, 0, width, total_height))

        # Draw header (days)
        for i, day in enumerate(self.DAY_ABBREV):
            x = time_col_width + i * day_width + day_width / 2
            self.calendar_canvas.create_text(
                x, header_height / 2,
                text=day,
                font=('Segoe UI', 11, 'bold'),
                fill=theme['fg']
            )

        # Draw time labels
        for i, hour in enumerate(hours):
            y = header_height + i * hour_height + hour_height / 2
            self.calendar_canvas.create_text(
                time_col_width / 2, y,
                text=f"{hour:02d}:00",
                font=('Segoe UI', 9),
                fill=theme['text_secondary']
            )

        # Draw grid lines
        for i in range(8):  # Vertical lines
            x = time_col_width + i * day_width
            self.calendar_canvas.create_line(
                x, header_height, x, total_height - 10,
                fill=theme['grid_line']
            )

        for i in range(len(hours) + 1):  # Horizontal lines
            y = header_height + i * hour_height
            self.calendar_canvas.create_line(
                time_col_width, y, width - 20, y,
                fill=theme['grid_line']
            )

        # Group shifts by day and find overlapping groups for side-by-side display
        for day in range(7):
            day_shifts = [s for s in self.shifts if s.day == day]
            # Find overlapping groups
            overlap_groups = self._group_overlapping_shifts(day_shifts)
            for group in overlap_groups:
                total_in_group = len(group)
                for idx, shift in enumerate(group):
                    self._draw_shift(
                        shift,
                        time_col_width,
                        header_height,
                        day_width,
                        hour_height,
                        idx,
                        total_in_group
                    )

    def _draw_shift(
        self,
        shift: Shift,
        time_col_width: float,
        header_height: float,
        day_width: float,
        hour_height: float,
        shift_index_on_day: int = 0,
        total_shifts_on_slot: int = 1
    ) -> None:
        """Draw a single shift on the calendar."""
        theme = self.theme_manager.theme

        # Calculate position (now with minute precision)
        start_offset = shift.start_hour + shift.start_minute / 60.0
        end_offset = shift.end_hour + shift.end_minute / 60.0

        # Adjust width for overlapping shifts (display side by side)
        slot_width = (day_width - 6) / total_shifts_on_slot
        x1 = time_col_width + shift.day * day_width + 3 + (shift_index_on_day * slot_width)
        x2 = x1 + slot_width - 2
        y1 = header_height + start_offset * hour_height + 2
        y2 = header_height + end_offset * hour_height - 2

        # Determine color based on shift type only
        if shift.shift_type == ShiftType.FIXED:
            color = theme['shift_fixed']
            border_color = theme['shift_fixed_border']
        else:
            color = theme['shift_flexible']
            border_color = theme['shift_flexible_border']

        # Draw rectangle
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
            font=('Segoe UI', 8, 'bold'),
            fill='#333333' if not self.theme_manager.dark_mode else '#ffffff',
            width=x2 - x1 - 4
        )

        # Draw time
        time_str = shift.time_str()
        self.calendar_canvas.create_text(
            (x1 + x2) / 2, y1 + 26,
            text=time_str,
            font=('Segoe UI', 7),
            fill='#555555' if not self.theme_manager.dark_mode else '#cccccc'
        )

        # Draw assigned users
        if shift.assigned_users:
            assigned_text = ", ".join(shift.assigned_users[:3])
            if len(shift.assigned_users) > 3:
                assigned_text += f" +{len(shift.assigned_users) - 3}"
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 40,
                text=assigned_text,
                font=('Segoe UI', 7, 'italic'),
                fill='#444444' if not self.theme_manager.dark_mode else '#bbbbbb',
                width=x2 - x1 - 4
            )
        else:
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 40,
                text=f"(need {shift.required_staff})",
                font=('Segoe UI', 7, 'italic'),
                fill=theme['text_muted'],
                width=x2 - x1 - 4
            )

    def _on_canvas_resize(self, event) -> None:
        """Handle canvas resize event."""
        self._draw_calendar()

    def _on_canvas_scroll(self, event) -> None:
        """Handle mouse wheel scrolling."""
        self.calendar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _refresh_all(self) -> None:
        """Refresh all UI elements."""
        self._refresh_users_list()
        self._refresh_shifts_list()
        self._draw_calendar()

    def _refresh_users_list(self) -> None:
        """Refresh the users listbox with shift counts."""
        self.users_listbox.delete(0, tk.END)
        for name, user in sorted(self.users.items()):
            # Count assigned shifts for this user
            shift_count = sum(
                1 for s in self.shifts if name in s.assigned_users
            )
            display = (
                f"  {name} - {shift_count} shifts "
                f"(max: {user.max_shifts_per_week})"
            )
            self.users_listbox.insert(tk.END, display)

    def _refresh_shifts_list(self) -> None:
        """Refresh the shifts listbox."""
        self.shifts_listbox.delete(0, tk.END)
        for shift in self.shifts:
            type_icon = "📌" if shift.shift_type == ShiftType.FIXED else "🔄"
            day_abbrev = self.DAY_ABBREV[shift.day]
            assigned_count = len(shift.assigned_users)
            display = (
                f"{type_icon} {shift.name} - {day_abbrev} {shift.time_str()} "
                f"[{assigned_count}/{shift.required_staff}]"
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
        dialog = UserDialog(
            self.root, "Add User", self.USER_COLORS, self.theme_manager
        )
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
            self.root, "Edit User", self.USER_COLORS, self.theme_manager, user
        )
        if dialog.result:
            new_name = dialog.result['name']
            if new_name != name:
                if new_name in self.users:
                    messagebox.showerror(
                        "Error", f"User '{new_name}' already exists!"
                    )
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
        dialog = ConflictDialog(
            self.root, self.users, self.conflicts, self.theme_manager
        )
        if dialog.result is not None:
            self.conflicts = dialog.result
            self._save_all()

    # ========================================================================
    # Shift Management
    # ========================================================================

    def _add_shift(self) -> None:
        """Open dialog to add a new shift."""
        dialog = ShiftDialog(
            self.root, "Add Shift", self.users, self.theme_manager
        )
        if dialog.result:
            self.shift_counter += 1
            shift = Shift(
                id=f"shift_{self.shift_counter}",
                name=dialog.result['name'],
                shift_type=dialog.result['shift_type'],
                day=dialog.result['day'],
                start_hour=dialog.result['start_hour'],
                start_minute=dialog.result['start_minute'],
                end_hour=dialog.result['end_hour'],
                end_minute=dialog.result['end_minute'],
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

        dialog = ShiftDialog(
            self.root, "Edit Shift", self.users, self.theme_manager, shift
        )
        if dialog.result:
            shift.name = dialog.result['name']
            shift.shift_type = dialog.result['shift_type']
            shift.day = dialog.result['day']
            shift.start_hour = dialog.result['start_hour']
            shift.start_minute = dialog.result['start_minute']
            shift.end_hour = dialog.result['end_hour']
            shift.end_minute = dialog.result['end_minute']
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

    def _manual_assign(self) -> None:
        """Open dialog to manually assign users to a shift."""
        selection = self.shifts_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "Warning", "Please select a shift to assign users."
            )
            return

        index = selection[0]
        shift = self.shifts[index]

        dialog = AssignUsersDialog(
            self.root, shift, self.users, self.shifts,
            self.conflicts, self.theme_manager
        )
        if dialog.result is not None:
            shift.assigned_users = dialog.result
            self._save_all()
            self._refresh_all()

    # ========================================================================
    # Scheduling
    # ========================================================================

    def _auto_schedule(self) -> None:
        """Run automatic scheduling with load balancing."""
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

        # Show distribution summary
        distribution = {}
        for name in self.users:
            distribution[name] = sum(
                1 for s in self.shifts if name in s.assigned_users
            )
        summary = "Shift Distribution:\n\n"
        for name, count in sorted(distribution.items()):
            max_shifts = self.users[name].max_shifts_per_week
            summary += f"  {name}: {count} shifts (max: {max_shifts})\n"
        messagebox.showinfo("Auto-Schedule Complete", summary)

    def _clear_assignments(self) -> None:
        """Clear all shift assignments."""
        if messagebox.askyesno("Confirm", "Clear all shift assignments?"):
            for shift in self.shifts:
                shift.assigned_users = []
            self._save_all()
            self._refresh_all()

    def _check_user_conflicts(self) -> None:
        """Check for users assigned to overlapping shifts."""
        conflicts_found = []
        for user_name in self.users:
            user_shifts = [s for s in self.shifts if user_name in s.assigned_users]
            for i, s1 in enumerate(user_shifts):
                for s2 in user_shifts[i + 1:]:
                    if s1.overlaps_with(s2):
                        conflicts_found.append((user_name, s1, s2))

        if not conflicts_found:
            messagebox.showinfo(
                "No Conflicts",
                "No users are double-booked on overlapping shifts!"
            )
        else:
            msg = "The following users have overlapping assignments:\n\n"
            for user, s1, s2 in conflicts_found:
                msg += (
                    f"• {user}:\n"
                    f"  {s1.name} ({self.DAY_ABBREV[s1.day]} {s1.time_str()})\n"
                    f"  {s2.name} ({self.DAY_ABBREV[s2.day]} {s2.time_str()})\n\n"
                )
            messagebox.showwarning("User Conflicts Found", msg)

    # ========================================================================
    # File Operations
    # ========================================================================

    def _save_all(self) -> None:
        """Save all data to files."""
        self.data_manager.save_users(self.users)
        self.data_manager.save_shifts(self.shifts)
        self.data_manager.save_conflicts(self.conflicts)
        self.settings['dark_mode'] = self.theme_manager.dark_mode
        self.data_manager.save_settings(self.settings)

    def _load_sample_data(self) -> None:
        """Load sample data for demonstration."""
        if self.users or self.shifts:
            if not messagebox.askyesno(
                "Confirm",
                "This will replace existing data. Continue?"
            ):
                return

        # Sample users with varied availability
        self.users = {
            'Alice': User(
                name='Alice',
                max_shifts_per_week=4,
                color='#FF6B6B',
                availability={
                    0: [],  # Monday unavailable
                    1: [TimeRange(9, 0, 17, 0)],
                    2: [TimeRange(9, 0, 17, 0)],
                    3: [TimeRange(9, 0, 17, 0)],
                    4: [TimeRange(9, 0, 17, 0)],
                    5: [TimeRange(10, 0, 14, 0)],
                    6: [],
                }
            ),
            'Bob': User(
                name='Bob',
                max_shifts_per_week=5,
                color='#4ECDC4',
                availability={
                    0: [TimeRange(8, 0, 20, 0)],
                    1: [TimeRange(8, 0, 20, 0)],
                    2: [TimeRange(8, 0, 20, 0)],
                    3: [TimeRange(8, 0, 20, 0)],
                    4: [TimeRange(8, 0, 20, 0)],
                    5: [],
                    6: [],
                }
            ),
            'Charlie': User(
                name='Charlie',
                max_shifts_per_week=3,
                color='#45B7D1',
                availability={
                    0: [TimeRange(6, 0, 14, 0)],
                    1: [TimeRange(6, 0, 14, 0)],
                    2: [TimeRange(6, 0, 14, 0)],
                    3: [TimeRange(6, 0, 14, 0)],
                    4: [],  # Friday unavailable
                    5: [TimeRange(8, 0, 16, 0)],
                    6: [TimeRange(8, 0, 16, 0)],
                }
            ),
            'Diana': User(
                name='Diana',
                max_shifts_per_week=4,
                color='#96CEB4'
            ),
            'Eve': User(
                name='Eve',
                max_shifts_per_week=5,
                color='#FFEAA7',
                availability={
                    0: [TimeRange(12, 0, 22, 0)],
                    1: [TimeRange(12, 0, 22, 0)],
                    2: [TimeRange(12, 0, 22, 0)],
                    3: [TimeRange(12, 0, 22, 0)],
                    4: [TimeRange(12, 0, 22, 0)],
                    5: [TimeRange(10, 0, 22, 0)],
                    6: [TimeRange(10, 0, 22, 0)],
                }
            ),
        }

        # Sample shifts
        self.shifts = [
            Shift(
                id='shift_1',
                name='Morning Reception',
                shift_type=ShiftType.FIXED,
                day=0,
                start_hour=9,
                start_minute=0,
                end_hour=12,
                end_minute=30,
                required_staff=2
            ),
            Shift(
                id='shift_2',
                name='Afternoon Support',
                shift_type=ShiftType.FIXED,
                day=0,
                start_hour=13,
                start_minute=0,
                end_hour=17,
                end_minute=0,
                required_staff=2
            ),
            Shift(
                id='shift_3',
                name='Team Meeting',
                shift_type=ShiftType.FLEXIBLE,
                day=2,
                start_hour=10,
                start_minute=0,
                end_hour=12,
                end_minute=0,
                required_staff=3
            ),
            Shift(
                id='shift_4',
                name='Training Session',
                shift_type=ShiftType.FLEXIBLE,
                day=3,
                start_hour=14,
                start_minute=30,
                end_hour=16,
                end_minute=30,
                required_staff=2
            ),
            Shift(
                id='shift_5',
                name='Weekly Review',
                shift_type=ShiftType.FIXED,
                day=4,
                start_hour=15,
                start_minute=0,
                end_hour=17,
                end_minute=0,
                required_staff=2
            ),
            Shift(
                id='shift_6',
                name='Evening Shift',
                shift_type=ShiftType.FIXED,
                day=1,
                start_hour=18,
                start_minute=0,
                end_hour=22,
                end_minute=0,
                required_staff=2
            ),
        ]
        self.shift_counter = 6

        # Sample conflicts
        self.conflicts = [('Alice', 'Bob')]

        self._save_all()
        self._refresh_all()
        messagebox.showinfo("Success", "Sample data loaded!")

    def _print_schedule(self) -> None:
        """Open print dialog for the schedule."""
        PrintDialog(self.root, self.shifts, self.users, self.theme_manager)

    def _toggle_dark_mode(self) -> None:
        """Toggle dark mode."""
        self.theme_manager.toggle()
        self.settings['dark_mode'] = self.theme_manager.dark_mode
        self.data_manager.save_settings(self.settings)
        self._apply_theme()

    def _show_about(self) -> None:
        """Show about dialog."""
        messagebox.showinfo(
            "About AutoSchedule",
            "AutoSchedule v2.0\n\n"
            "Automatic Shift Scheduling Application\n\n"
            "Features:\n"
            "• User profile management with minute-level availability\n"
            "• Fixed and flexible shift types\n"
            "• 24-hour, 7-day availability settings\n"
            "• Conflict pair management\n"
            "• Shift overlap detection\n"
            "• Manual and automatic scheduling\n"
            "• Dark mode support\n"
            "• Print/export functionality\n\n"
            "© 2026 AutoSchedule"
        )


# ============================================================================
# DIALOGS
# ============================================================================

class UserDialog:
    """Dialog for adding/editing users with time range availability."""

    DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        colors: List[str],
        theme_manager: ThemeManager,
        user: User = None
    ):
        """Initialize user dialog."""
        self.result = None
        self.colors = colors
        self.user = user
        self.theme = theme_manager.theme
        self.availability: Dict[int, List[TimeRange]] = {}

        # Initialize availability from user or defaults
        if user:
            for day in range(7):
                self.availability[day] = list(user.availability.get(day, []))
        else:
            for day in range(7):
                self.availability[day] = [TimeRange(0, 0, 24, 0)]

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("750x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])

        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 750) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
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
            to=21,
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
            text="Availability (add time ranges for each day):",
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor=tk.W, pady=(0, 10))

        # Create scrollable availability frame
        avail_container = ttk.Frame(main_frame)
        avail_container.pack(fill=tk.BOTH, expand=True)

        # Canvas for scrolling
        canvas = tk.Canvas(
            avail_container,
            bg=self.theme['card_bg'],
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            avail_container, orient=tk.VERTICAL, command=canvas.yview
        )
        self.avail_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas_frame = canvas.create_window(
            (0, 0), window=self.avail_frame, anchor=tk.NW
        )

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_frame, width=event.width)

        self.avail_frame.bind('<Configure>', configure_scroll)

        # Day rows with time range lists
        self.day_frames = {}
        self.range_listboxes = {}

        for day_idx, day_name in enumerate(self.DAYS):
            day_frame = ttk.LabelFrame(
                self.avail_frame,
                text=f"  {day_name}  ",
                padding=5
            )
            day_frame.pack(fill=tk.X, pady=3, padx=5)
            self.day_frames[day_idx] = day_frame

            # Left side: listbox with ranges
            list_frame = ttk.Frame(day_frame)
            list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lb = tk.Listbox(
                list_frame,
                height=2,
                font=('Segoe UI', 9),
                bg=self.theme['listbox_bg'],
                fg=self.theme['listbox_fg'],
                selectbackground=self.theme['listbox_select_bg']
            )
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.range_listboxes[day_idx] = lb
            self._refresh_day_ranges(day_idx)

            # Right side: buttons
            btn_frame = ttk.Frame(day_frame)
            btn_frame.pack(side=tk.RIGHT, padx=(10, 0))

            ttk.Button(
                btn_frame,
                text="+ Add",
                width=8,
                command=lambda d=day_idx: self._add_range(d)
            ).pack(pady=1)

            ttk.Button(
                btn_frame,
                text="- Remove",
                width=8,
                command=lambda d=day_idx: self._remove_range(d)
            ).pack(pady=1)

            ttk.Button(
                btn_frame,
                text="All Day",
                width=8,
                command=lambda d=day_idx: self._set_all_day(d)
            ).pack(pady=1)

            ttk.Button(
                btn_frame,
                text="Clear",
                width=8,
                command=lambda d=day_idx: self._clear_day(d)
            ).pack(pady=1)

        # Quick actions
        quick_frame = ttk.Frame(main_frame)
        quick_frame.pack(fill=tk.X, pady=10)

        ttk.Button(
            quick_frame,
            text="All Days Available",
            command=self._select_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            quick_frame,
            text="Clear All",
            command=self._clear_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            quick_frame,
            text="Weekdays 9-5",
            command=self._weekdays_business
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

    def _refresh_day_ranges(self, day: int) -> None:
        """Refresh the listbox for a specific day."""
        lb = self.range_listboxes[day]
        lb.delete(0, tk.END)
        for tr in self.availability[day]:
            lb.insert(tk.END, f"  {tr}")

    def _add_range(self, day: int) -> None:
        """Add a time range to a day."""
        dialog = TimeRangeDialog(self.dialog, self.theme)
        if dialog.result:
            new_range = TimeRange(
                dialog.result['start_hour'],
                dialog.result['start_minute'],
                dialog.result['end_hour'],
                dialog.result['end_minute']
            )
            self.availability[day].append(new_range)
            self._refresh_day_ranges(day)

    def _remove_range(self, day: int) -> None:
        """Remove selected time range from a day."""
        lb = self.range_listboxes[day]
        selection = lb.curselection()
        if selection:
            idx = selection[0]
            self.availability[day].pop(idx)
            self._refresh_day_ranges(day)

    def _set_all_day(self, day: int) -> None:
        """Set day to all-day availability."""
        self.availability[day] = [TimeRange(0, 0, 24, 0)]
        self._refresh_day_ranges(day)

    def _clear_day(self, day: int) -> None:
        """Clear all availability for a day."""
        self.availability[day] = []
        self._refresh_day_ranges(day)

    def _select_all(self) -> None:
        """Set all days to all-day availability."""
        for day in range(7):
            self.availability[day] = [TimeRange(0, 0, 24, 0)]
            self._refresh_day_ranges(day)

    def _clear_all(self) -> None:
        """Clear all availability."""
        for day in range(7):
            self.availability[day] = []
            self._refresh_day_ranges(day)

    def _weekdays_business(self) -> None:
        """Set weekdays to 9am-5pm."""
        for day in range(7):
            if day < 5:  # Mon-Fri
                self.availability[day] = [TimeRange(9, 0, 17, 0)]
            else:
                self.availability[day] = []
            self._refresh_day_ranges(day)

    def _save(self) -> None:
        """Save and close dialog."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required!")
            return

        self.result = {
            'name': name,
            'max_shifts': self.max_shifts_var.get(),
            'availability': self.availability,
            'color': self.color_var.get()
        }
        self.dialog.destroy()


class TimeRangeDialog:
    """Dialog for entering a time range."""

    def __init__(self, parent: tk.Toplevel, theme: dict):
        """Initialize time range dialog."""
        self.result = None
        self.theme = theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Add Time Range")
        self.dialog.geometry("300x180")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=theme['bg'])

        # Center
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 300) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 180) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        """Create widgets."""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Start time
        start_frame = ttk.Frame(main_frame)
        start_frame.pack(fill=tk.X, pady=5)

        ttk.Label(start_frame, text="Start Time:", width=12).pack(side=tk.LEFT)
        self.start_hour_var = tk.IntVar(value=9)
        ttk.Spinbox(
            start_frame, from_=0, to=23,
            textvariable=self.start_hour_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Label(start_frame, text=":").pack(side=tk.LEFT)
        self.start_min_var = tk.IntVar(value=0)
        ttk.Spinbox(
            start_frame, from_=0, to=59,
            textvariable=self.start_min_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT, padx=2)

        # End time
        end_frame = ttk.Frame(main_frame)
        end_frame.pack(fill=tk.X, pady=5)

        ttk.Label(end_frame, text="End Time:", width=12).pack(side=tk.LEFT)
        self.end_hour_var = tk.IntVar(value=17)
        ttk.Spinbox(
            end_frame, from_=0, to=24,
            textvariable=self.end_hour_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Label(end_frame, text=":").pack(side=tk.LEFT)
        self.end_min_var = tk.IntVar(value=0)
        ttk.Spinbox(
            end_frame, from_=0, to=59,
            textvariable=self.end_min_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT, padx=2)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(
            btn_frame, text="Cancel", command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)
        ttk.Button(
            btn_frame, text="Add", command=self._save
        ).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        """Save and close."""
        start_h = self.start_hour_var.get()
        start_m = self.start_min_var.get()
        end_h = self.end_hour_var.get()
        end_m = self.end_min_var.get()

        # Validate that 24:xx is only allowed with minute=0
        if end_h == 24 and end_m != 0:
            messagebox.showerror("Error", "End time of 24:00 cannot have non-zero minutes!")
            return

        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m

        if end_mins <= start_mins:
            messagebox.showerror("Error", "End time must be after start time!")
            return

        self.result = {
            'start_hour': start_h,
            'start_minute': start_m,
            'end_hour': end_h,
            'end_minute': end_m
        }
        self.dialog.destroy()


class ShiftDialog:
    """Dialog for adding/editing shifts."""

    DAYS = [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday',
        'Friday', 'Saturday', 'Sunday'
    ]

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        users: Dict[str, User],
        theme_manager: ThemeManager,
        shift: Shift = None
    ):
        """Initialize shift dialog."""
        self.result = None
        self.users = users
        self.shift = shift
        self.theme = theme_manager.theme

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("450x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])

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
            row=0, column=1, columnspan=3, sticky=tk.W, pady=5
        )

        # Shift Type
        ttk.Label(main_frame, text="Shift Type:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.type_var = tk.StringVar(
            value=self.shift.shift_type.value if self.shift else "fixed"
        )
        type_frame = ttk.Frame(main_frame)
        type_frame.grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=5)

        ttk.Radiobutton(
            type_frame,
            text="📌 Fixed",
            variable=self.type_var,
            value="fixed"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            type_frame,
            text="🔄 Flexible",
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
        day_combo.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=5)

        # Start Time (hour and minute)
        ttk.Label(main_frame, text="Start Time:").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        start_frame = ttk.Frame(main_frame)
        start_frame.grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=5)

        self.start_hour_var = tk.IntVar(
            value=self.shift.start_hour if self.shift else 9
        )
        ttk.Spinbox(
            start_frame, from_=0, to=23,
            textvariable=self.start_hour_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT)
        ttk.Label(start_frame, text=":").pack(side=tk.LEFT)
        self.start_min_var = tk.IntVar(
            value=self.shift.start_minute if self.shift else 0
        )
        ttk.Spinbox(
            start_frame, from_=0, to=59,
            textvariable=self.start_min_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT)

        # End Time (hour and minute)
        ttk.Label(main_frame, text="End Time:").grid(
            row=4, column=0, sticky=tk.W, pady=5
        )
        end_frame = ttk.Frame(main_frame)
        end_frame.grid(row=4, column=1, columnspan=3, sticky=tk.W, pady=5)

        self.end_hour_var = tk.IntVar(
            value=self.shift.end_hour if self.shift else 17
        )
        ttk.Spinbox(
            end_frame, from_=0, to=24,
            textvariable=self.end_hour_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT)
        ttk.Label(end_frame, text=":").pack(side=tk.LEFT)
        self.end_min_var = tk.IntVar(
            value=self.shift.end_minute if self.shift else 0
        )
        ttk.Spinbox(
            end_frame, from_=0, to=59,
            textvariable=self.end_min_var, width=5, format="%02.0f"
        ).pack(side=tk.LEFT)

        # Required Staff (minimum 2)
        ttk.Label(main_frame, text="Required Staff:").grid(
            row=5, column=0, sticky=tk.W, pady=5
        )
        self.staff_var = tk.IntVar(
            value=self.shift.required_staff if self.shift else 2
        )
        staff_spin = ttk.Spinbox(
            main_frame,
            from_=2,
            to=20,
            textvariable=self.staff_var,
            width=5
        )
        staff_spin.grid(row=5, column=1, sticky=tk.W, pady=5)

        # Note
        note_label = ttk.Label(
            main_frame,
            text="Note: Flexible shifts may be moved to optimal\n"
                 "times during auto-scheduling.",
            font=('Segoe UI', 9, 'italic'),
            foreground=self.theme['text_secondary']
        )
        note_label.grid(row=6, column=0, columnspan=4, pady=15)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=4, pady=(10, 0))

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

        start_h = self.start_hour_var.get()
        start_m = self.start_min_var.get()
        end_h = self.end_hour_var.get()
        end_m = self.end_min_var.get()

        # Validate that 24:xx is only allowed with minute=0
        if end_h == 24 and end_m != 0:
            messagebox.showerror("Error", "End time of 24:00 cannot have non-zero minutes!")
            return

        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m

        if end_mins <= start_mins:
            messagebox.showerror("Error", "End time must be after start time!")
            return

        self.result = {
            'name': name,
            'shift_type': ShiftType(self.type_var.get()),
            'day': self.DAYS.index(self.day_var.get()),
            'start_hour': start_h,
            'start_minute': start_m,
            'end_hour': end_h,
            'end_minute': end_m,
            'required_staff': self.staff_var.get()
        }
        self.dialog.destroy()


class AssignUsersDialog:
    """Dialog for manually assigning users to a shift."""

    def __init__(
        self,
        parent: tk.Tk,
        shift: Shift,
        users: Dict[str, User],
        all_shifts: List[Shift],
        conflicts: List[Tuple[str, str]],
        theme_manager: ThemeManager
    ):
        """Initialize assign users dialog."""
        self.result = None
        self.shift = shift
        self.users = users
        self.all_shifts = all_shifts
        self.conflicts = set()
        for c1, c2 in conflicts:
            self.conflicts.add((c1, c2))
            self.conflicts.add((c2, c1))
        self.theme = theme_manager.theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Assign Users to: {shift.name}")
        self.dialog.geometry("500x450")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])

        # Center
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 500) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _check_user_overlap(self, user_name: str) -> bool:
        """Check if user has overlapping shift."""
        for other_shift in self.all_shifts:
            if other_shift.id == self.shift.id:
                continue
            if user_name in other_shift.assigned_users:
                if self.shift.overlaps_with(other_shift):
                    return True
        return False

    def _create_widgets(self) -> None:
        """Create widgets."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Shift info
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        info_text = (
            f"Shift: {self.shift.name}\n"
            f"Day: {day_names[self.shift.day]}\n"
            f"Time: {self.shift.time_str()}\n"
            f"Required: {self.shift.required_staff} staff"
        )
        ttk.Label(
            main_frame, text=info_text, font=('Segoe UI', 10)
        ).pack(anchor=tk.W, pady=(0, 15))

        # Available users
        ttk.Label(
            main_frame, text="Select users to assign:",
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor=tk.W)

        # Checkbuttons for users
        self.user_vars: Dict[str, tk.BooleanVar] = {}

        users_frame = ttk.Frame(main_frame)
        users_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        canvas = tk.Canvas(
            users_frame, bg=self.theme['card_bg'], highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            users_frame, orient=tk.VERTICAL, command=canvas.yview
        )
        inner_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.create_window((0, 0), window=inner_frame, anchor=tk.NW)

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind('<Configure>', configure_scroll)

        for name, user in sorted(self.users.items()):
            var = tk.BooleanVar(value=name in self.shift.assigned_users)
            self.user_vars[name] = var

            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, pady=2)

            cb = ttk.Checkbutton(
                frame, text=name, variable=var
            )
            cb.pack(side=tk.LEFT)

            # Check availability
            available = user.is_available(
                self.shift.day,
                self.shift.start_hour, self.shift.start_minute,
                self.shift.end_hour, self.shift.end_minute
            )

            # Check for overlapping shifts
            has_overlap = self._check_user_overlap(name)

            # Status indicators
            status_parts = []
            if not available:
                status_parts.append("❌ unavailable")
            if has_overlap:
                status_parts.append("⚠️ overlap")

            if status_parts:
                ttk.Label(
                    frame,
                    text=f"({', '.join(status_parts)})",
                    foreground=self.theme['danger'],
                    font=('Segoe UI', 9)
                ).pack(side=tk.LEFT, padx=10)
            else:
                ttk.Label(
                    frame,
                    text="✓ available",
                    foreground=self.theme['success'],
                    font=('Segoe UI', 9)
                ).pack(side=tk.LEFT, padx=10)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_frame, text="Cancel", command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame, text="Assign", command=self._save
        ).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        """Save assignments."""
        assigned = [name for name, var in self.user_vars.items() if var.get()]

        # Check for conflicts among assigned users
        for i, u1 in enumerate(assigned):
            for u2 in assigned[i + 1:]:
                if (u1, u2) in self.conflicts:
                    messagebox.showerror(
                        "Conflict",
                        f"{u1} and {u2} have a conflict and cannot be "
                        "assigned to the same shift."
                    )
                    return

        # Block overlaps (no double-booking)
        overlapping_users = [
            name for name in assigned if self._check_user_overlap(name)
        ]
        if overlapping_users:
            messagebox.showerror(
                "Overlap Detected",
                "The following users are already scheduled on overlapping "
                f"shifts and cannot be assigned to this shift:\n\n"
                f"{', '.join(overlapping_users)}"
            )
            return

        self.result = assigned
        self.dialog.destroy()


class ConflictDialog:
    """Dialog for managing conflict pairs."""

    def __init__(
        self,
        parent: tk.Tk,
        users: Dict[str, User],
        conflicts: List[Tuple[str, str]],
        theme_manager: ThemeManager
    ):
        """Initialize conflict dialog."""
        self.result = None
        self.users = users
        self.conflicts = list(conflicts)
        self.theme = theme_manager.theme

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Manage Conflict Pairs")
        self.dialog.geometry("450x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])

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
            foreground=self.theme['text_secondary']
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
            font=('Segoe UI', 10),
            bg=self.theme['listbox_bg'],
            fg=self.theme['listbox_fg'],
            selectbackground=self.theme['listbox_select_bg']
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
            command=self._cancel
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
            messagebox.showwarning(
                "Warning", "Please select a conflict to remove."
            )
            return

        index = selection[0]
        self.conflicts.pop(index)
        self._refresh_list()

    def _cancel(self) -> None:
        """Cancel without saving."""
        self.result = None
        self.dialog.destroy()

    def _save(self) -> None:
        """Save and close dialog."""
        self.result = self.conflicts
        self.dialog.destroy()


class PrintDialog:
    """Dialog for printing/exporting the schedule."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday']

    def __init__(
        self,
        parent: tk.Tk,
        shifts: List[Shift],
        users: Dict[str, User],
        theme_manager: ThemeManager
    ):
        """Initialize print dialog."""
        self.shifts = shifts
        self.users = users
        self.theme = theme_manager.theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Print Schedule")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        self.dialog.configure(bg=self.theme['bg'])

        # Center
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 800) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self) -> None:
        """Create widgets."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text="Schedule Preview",
            font=('Segoe UI', 14, 'bold')
        ).pack(anchor=tk.W, pady=(0, 10))

        # Text widget for preview
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text_widget = tk.Text(
            text_frame,
            font=('Consolas', 10),
            bg='white',
            fg='black',
            wrap=tk.NONE
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        y_scroll = ttk.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=self.text_widget.yview
        )
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        x_scroll = ttk.Scrollbar(
            main_frame, orient=tk.HORIZONTAL, command=self.text_widget.xview
        )
        x_scroll.pack(fill=tk.X)

        self.text_widget.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set
        )

        # Generate content
        self._generate_content()

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_frame, text="Close", command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame, text="Copy to Clipboard", command=self._copy_to_clipboard
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame, text="Save as Text File", command=self._save_to_file
        ).pack(side=tk.RIGHT, padx=5)

    def _generate_content(self) -> None:
        """Generate printable schedule content."""
        lines = []
        lines.append("=" * 80)
        lines.append("                        WEEKLY SCHEDULE")
        lines.append(
            f"                Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        lines.append("=" * 80)
        lines.append("")

        # Group shifts by day
        for day_idx, day_name in enumerate(self.DAYS):
            day_shifts = [s for s in self.shifts if s.day == day_idx]
            day_shifts.sort(key=lambda s: s.start_hour * 60 + s.start_minute)

            lines.append(f"┌{'─' * 78}┐")
            lines.append(f"│ {day_name.upper():^76} │")
            lines.append(f"├{'─' * 78}┤")

            if not day_shifts:
                lines.append(f"│ {'No shifts scheduled':^76} │")
            else:
                for shift in day_shifts:
                    type_str = (
                        "FIXED" if shift.shift_type == ShiftType.FIXED
                        else "FLEX"
                    )
                    time_str = shift.time_str()
                    assigned = ", ".join(shift.assigned_users) or "(unassigned)"

                    line1 = f"  [{type_str}] {shift.name}"
                    line2 = f"          Time: {time_str}  |  Staff: {assigned}"

                    lines.append(f"│ {line1:<76} │")
                    lines.append(f"│ {line2:<76} │")
                    lines.append(f"│ {' ' * 76} │")

            lines.append(f"└{'─' * 78}┘")
            lines.append("")

        # Staff summary
        lines.append("=" * 80)
        lines.append("                        STAFF SUMMARY")
        lines.append("=" * 80)
        lines.append("")

        for name, user in sorted(self.users.items()):
            shift_count = sum(
                1 for s in self.shifts if name in s.assigned_users
            )
            lines.append(
                f"  {name}: {shift_count} shifts "
                f"(max: {user.max_shifts_per_week})"
            )

        lines.append("")
        lines.append("=" * 80)

        self.text_widget.insert('1.0', '\n'.join(lines))
        self.text_widget.configure(state='disabled')

    def _copy_to_clipboard(self) -> None:
        """Copy content to clipboard."""
        self.text_widget.configure(state='normal')
        content = self.text_widget.get('1.0', tk.END)
        self.text_widget.configure(state='disabled')
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(content)
        messagebox.showinfo("Copied", "Schedule copied to clipboard!")

    def _save_to_file(self) -> None:
        """Save content to text file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfilename=f"schedule_{datetime.now().strftime('%Y%m%d')}.txt"
        )

        if filename:
            self.text_widget.configure(state='normal')
            content = self.text_widget.get('1.0', tk.END)
            self.text_widget.configure(state='disabled')
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Schedule saved to:\n{filename}")


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
