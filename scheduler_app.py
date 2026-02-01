"""
Multi-Week Scheduler Application v3
Full-featured scheduling app with all capabilities from v2 plus multi-week support.

Features:
- Multi-week scheduling with week navigation
- User profile management with availability
- Fixed and flexible shift types
- Minute-level time precision
- Load-balanced auto-scheduling
- Conflict pair management
- Dark mode support
- Print/export functionality
- Overlapping shifts displayed side-by-side
- No double-booking enforcement
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
import uuid
import json
from pathlib import Path
import copy
import random


# =============================================================================
# DATA MODELS
# =============================================================================

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

    def to_dict(self) -> dict:
        return {
            'start_hour': self.start_hour,
            'start_minute': self.start_minute,
            'end_hour': self.end_hour,
            'end_minute': self.end_minute
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TimeRange':
        return cls(
            start_hour=data['start_hour'],
            start_minute=data['start_minute'],
            end_hour=data['end_hour'],
            end_minute=data['end_minute']
        )

    def __str__(self) -> str:
        return f"{self.start_hour:02d}:{self.start_minute:02d} - {self.end_hour:02d}:{self.end_minute:02d}"


@dataclass
class User:
    """Represents a user/employee with availability settings."""
    id: str
    name: str
    max_shifts_per_week: int = 5
    availability: Dict[int, List[TimeRange]] = field(default_factory=dict)
    color: str = "#4A90D9"

    def __post_init__(self):
        """Initialize default availability (all day available)."""
        if not self.availability:
            for day in range(7):
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

        for time_range in self.availability.get(day_key, []):
            avail_start, avail_end = time_range.to_minutes()
            if avail_start <= check_start and avail_end >= check_end:
                return True
        return False

    def to_dict(self) -> dict:
        availability_dict = {}
        for day, ranges in self.availability.items():
            availability_dict[str(day)] = [r.to_dict() for r in ranges]
        return {
            'id': self.id,
            'name': self.name,
            'max_shifts_per_week': self.max_shifts_per_week,
            'availability': availability_dict,
            'color': self.color
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        availability = {}
        for day_str, ranges in data.get('availability', {}).items():
            day = int(day_str)
            time_ranges = []
            for item in ranges:
                if isinstance(item, dict):
                    time_ranges.append(TimeRange.from_dict(item))
                elif isinstance(item, int):
                    time_ranges.append(TimeRange(item, 0, item + 1, 0))
            availability[day] = time_ranges
        return cls(
            id=data.get('id', str(uuid.uuid4())[:8]),
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
    start_minute: int
    end_hour: int
    end_minute: int
    week_key: str  # Format: "YYYY-WW" (ISO week)
    required_staff: int = 2
    assigned_users: List[str] = field(default_factory=list)
    is_split: bool = False
    original_shift_id: Optional[str] = None

    def duration_minutes(self) -> int:
        start = self.start_hour * 60 + self.start_minute
        end = self.end_hour * 60 + self.end_minute
        return end - start

    def to_time_range(self) -> TimeRange:
        return TimeRange(self.start_hour, self.start_minute,
                        self.end_hour, self.end_minute)

    def overlaps_with(self, other: 'Shift') -> bool:
        """Check if this shift overlaps with another on the same day."""
        if self.day != other.day:
            return False
        return self.to_time_range().overlaps(other.to_time_range())

    def time_str(self) -> str:
        return f"{self.start_hour:02d}:{self.start_minute:02d}-{self.end_hour:02d}:{self.end_minute:02d}"

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'shift_type': self.shift_type.value,
            'day': self.day,
            'start_hour': self.start_hour,
            'start_minute': self.start_minute,
            'end_hour': self.end_hour,
            'end_minute': self.end_minute,
            'week_key': self.week_key,
            'required_staff': self.required_staff,
            'assigned_users': self.assigned_users,
            'is_split': self.is_split,
            'original_shift_id': self.original_shift_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Shift':
        return cls(
            id=data['id'],
            name=data['name'],
            shift_type=ShiftType(data['shift_type']),
            day=data['day'],
            start_hour=data['start_hour'],
            start_minute=data.get('start_minute', 0),
            end_hour=data['end_hour'],
            end_minute=data.get('end_minute', 0),
            week_key=data.get('week_key', ''),
            required_staff=data.get('required_staff', 2),
            assigned_users=data.get('assigned_users', []),
            is_split=data.get('is_split', False),
            original_shift_id=data.get('original_shift_id')
        )


@dataclass
class WeekState:
    """State container for a single week."""
    week_key: str
    week_start: date
    shifts: Dict[str, Shift] = field(default_factory=dict)
    is_loaded: bool = False
    is_dirty: bool = False

    def add_shift(self, shift: Shift) -> None:
        self.shifts[shift.id] = shift
        self.is_dirty = True

    def remove_shift(self, shift_id: str) -> Optional[Shift]:
        self.is_dirty = True
        return self.shifts.pop(shift_id, None)

    def clear_shifts(self) -> None:
        self.shifts.clear()
        self.is_dirty = True

    def get_shifts_for_day(self, day: int) -> List[Shift]:
        return [s for s in self.shifts.values() if s.day == day]

    def get_all_shifts(self) -> List[Shift]:
        return list(self.shifts.values())


# =============================================================================
# STATE MANAGER
# =============================================================================

class SchedulerStateManager:
    """Manages week-based state with lazy loading and persistence."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = Path(__file__).parent / "scheduler_data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self._week_states: Dict[str, WeekState] = {}
        self.users: Dict[str, User] = {}
        self.conflicts: List[Tuple[str, str]] = []
        self.settings: dict = {'dark_mode': False}
        self._current_week_key: Optional[str] = None

        self._load_users()
        self._load_conflicts()
        self._load_settings()

    @staticmethod
    def get_week_key(d: date) -> str:
        """Get ISO week key for a date (YYYY-WW format)."""
        iso_cal = d.isocalendar()
        return f"{iso_cal[0]}-W{iso_cal[1]:02d}"

    @staticmethod
    def get_week_start(d: date) -> date:
        """Get Monday of the week containing the given date."""
        return d - timedelta(days=d.weekday())

    @staticmethod
    def week_key_to_start_date(week_key: str) -> date:
        """Convert week key to the Monday of that week."""
        try:
            year, week = week_key.split('-W')
            return datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()
        except:
            return date.today()

    def get_or_create_week_state(self, week_key: str) -> WeekState:
        """Lazy load or create week state."""
        if week_key not in self._week_states:
            week_start = self.week_key_to_start_date(week_key)
            state = WeekState(week_key=week_key, week_start=week_start)
            self._load_week_data(state)
            self._week_states[week_key] = state
        return self._week_states[week_key]

    def get_current_week_state(self) -> Optional[WeekState]:
        if self._current_week_key:
            return self.get_or_create_week_state(self._current_week_key)
        return None

    def set_current_week(self, week_key: str) -> WeekState:
        self._current_week_key = week_key
        return self.get_or_create_week_state(week_key)

    def _get_week_file_path(self, week_key: str) -> Path:
        return self.data_dir / f"week_{week_key}.json"

    def _load_week_data(self, state: WeekState) -> None:
        file_path = self._get_week_file_path(state.week_key)
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                for shift_data in data.get('shifts', []):
                    shift = Shift.from_dict(shift_data)
                    state.shifts[shift.id] = shift
                state.is_dirty = False
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading week {state.week_key}: {e}")
        state.is_loaded = True

    def save_week_data(self, week_key: str) -> None:
        if week_key not in self._week_states:
            return
        state = self._week_states[week_key]
        if not state.is_dirty:
            return
        file_path = self._get_week_file_path(week_key)
        data = {
            'week_key': week_key,
            'shifts': [s.to_dict() for s in state.shifts.values()]
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        state.is_dirty = False

    def _load_users(self) -> None:
        file_path = self.data_dir / "users.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                for user_data in data:
                    user = User.from_dict(user_data)
                    self.users[user.id] = user
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading users: {e}")

    def save_users(self) -> None:
        file_path = self.data_dir / "users.json"
        data = [user.to_dict() for user in self.users.values()]
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_conflicts(self) -> None:
        file_path = self.data_dir / "conflicts.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                self.conflicts = [tuple(pair) for pair in data]
            except (json.JSONDecodeError, KeyError):
                self.conflicts = []

    def save_conflicts(self) -> None:
        file_path = self.data_dir / "conflicts.json"
        with open(file_path, 'w') as f:
            json.dump(self.conflicts, f, indent=2)

    def _load_settings(self) -> None:
        file_path = self.data_dir / "settings.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    self.settings = json.load(f)
            except (json.JSONDecodeError, KeyError):
                self.settings = {'dark_mode': False}

    def save_settings(self) -> None:
        file_path = self.data_dir / "settings.json"
        with open(file_path, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def save_all(self) -> None:
        for week_key in self._week_states:
            self.save_week_data(week_key)
        self.save_users()
        self.save_conflicts()
        self.save_settings()

    def add_user(self, name: str, max_shifts: int = 5, color: str = "#4A90D9",
                 availability: Dict[int, List[TimeRange]] = None) -> User:
        user_id = str(uuid.uuid4())[:8]
        user = User(
            id=user_id,
            name=name,
            max_shifts_per_week=max_shifts,
            color=color,
            availability=availability or {}
        )
        self.users[user_id] = user
        return user

    def remove_user(self, user_id: str) -> None:
        if user_id in self.users:
            del self.users[user_id]
            self.conflicts = [(a, b) for a, b in self.conflicts
                            if a != user_id and b != user_id]
            for state in self._week_states.values():
                for shift in state.shifts.values():
                    if user_id in shift.assigned_users:
                        shift.assigned_users.remove(user_id)
                        state.is_dirty = True

    def add_shift(self, week_key: str, name: str, shift_type: ShiftType,
                  day: int, start_hour: int, start_minute: int,
                  end_hour: int, end_minute: int,
                  required_staff: int = 2) -> Shift:
        shift_id = str(uuid.uuid4())[:8]
        shift = Shift(
            id=shift_id,
            name=name,
            shift_type=shift_type,
            day=day,
            start_hour=start_hour,
            start_minute=start_minute,
            end_hour=end_hour,
            end_minute=end_minute,
            week_key=week_key,
            required_staff=required_staff
        )
        state = self.get_or_create_week_state(week_key)
        state.add_shift(shift)
        return shift

    def remove_shift(self, week_key: str, shift_id: str) -> Optional[Shift]:
        state = self.get_or_create_week_state(week_key)
        return state.remove_shift(shift_id)

    def clear_week(self, week_key: str) -> int:
        state = self.get_or_create_week_state(week_key)
        count = len(state.shifts)
        state.clear_shifts()
        return count


# =============================================================================
# SCHEDULER ENGINE
# =============================================================================

class Scheduler:
    """Handles automatic scheduling logic with load balancing."""

    def __init__(self, users: Dict[str, User], conflicts: List[Tuple[str, str]]):
        self.users = users
        self.conflicts = set()
        for pair in conflicts:
            self.conflicts.add((pair[0], pair[1]))
            self.conflicts.add((pair[1], pair[0]))

    def has_conflict(self, assigned: List[str], candidate: str) -> bool:
        for user_id in assigned:
            if (user_id, candidate) in self.conflicts:
                return True
        return False

    def check_user_overlap(self, user_id: str, shift: Shift,
                          all_shifts: List[Shift]) -> bool:
        for other_shift in all_shifts:
            if other_shift.id == shift.id:
                continue
            if user_id in other_shift.assigned_users:
                if shift.overlaps_with(other_shift):
                    return True
        return False

    def get_available_users(self, shift: Shift, shifts_worked: Dict[str, int],
                           all_shifts: List[Shift]) -> List[str]:
        candidates = []
        for user_id, user in self.users.items():
            if shifts_worked.get(user_id, 0) >= user.max_shifts_per_week:
                continue
            if not user.is_available(shift.day, shift.start_hour, shift.start_minute,
                                    shift.end_hour, shift.end_minute):
                continue
            if self.check_user_overlap(user_id, shift, all_shifts):
                continue
            candidates.append(user_id)
        return candidates

    def schedule_shifts(self, shifts: List[Shift]) -> List[Shift]:
        """Auto-schedule with load balancing."""
        scheduled_shifts = [copy.deepcopy(s) for s in shifts]
        shifts_worked = {uid: 0 for uid in self.users}

        for shift in scheduled_shifts:
            for user_id in shift.assigned_users:
                if user_id in shifts_worked:
                    shifts_worked[user_id] += 1

        fixed_shifts = [s for s in scheduled_shifts if s.shift_type == ShiftType.FIXED]
        flexible_shifts = [s for s in scheduled_shifts if s.shift_type == ShiftType.FLEXIBLE]

        for shift in fixed_shifts:
            self._assign_shift_balanced(shift, shifts_worked, scheduled_shifts)

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

    def _assign_shift_balanced(self, shift: Shift, shifts_worked: Dict[str, int],
                               all_shifts: List[Shift]) -> None:
        valid_assigned = []
        for user_id in shift.assigned_users:
            if user_id in self.users:
                if not self.check_user_overlap(user_id, shift, all_shifts):
                    valid_assigned.append(user_id)
        shift.assigned_users = valid_assigned

        needed = shift.required_staff - len(shift.assigned_users)
        if needed <= 0:
            return

        candidates = self.get_available_users(shift, shifts_worked, all_shifts)
        candidates = [c for c in candidates if c not in shift.assigned_users]

        total_slots = sum(s.required_staff for s in all_shifts)
        num_users = max(len(self.users), 1)
        target = total_slots / num_users

        def balance_score(user_id: str) -> float:
            current = shifts_worked.get(user_id, 0)
            below_target = target - current
            capacity = self.users[user_id].max_shifts_per_week - current
            return (below_target * 10) + capacity + random.random() * 0.1

        candidates.sort(key=balance_score, reverse=True)

        for candidate in candidates:
            if len(shift.assigned_users) >= shift.required_staff:
                break
            if not self.has_conflict(shift.assigned_users, candidate):
                shift.assigned_users.append(candidate)
                shifts_worked[candidate] = shifts_worked.get(candidate, 0) + 1

    def _find_best_slot(self, shift: Shift, shifts_worked: Dict[str, int],
                        all_shifts: List[Shift]) -> Optional[Tuple[int, int, int, int, int]]:
        duration = shift.duration_minutes()
        best_slot = None
        best_score = -1

        for day in range(7):
            for start_hour in range(24):
                for start_minute in [0, 30]:
                    end_minutes = start_hour * 60 + start_minute + duration
                    if end_minutes > 24 * 60:
                        continue
                    end_hour = end_minutes // 60
                    end_minute = end_minutes % 60

                    test_shift = copy.deepcopy(shift)
                    test_shift.day = day
                    test_shift.start_hour = start_hour
                    test_shift.start_minute = start_minute
                    test_shift.end_hour = end_hour
                    test_shift.end_minute = end_minute

                    has_overlap = any(
                        other.id != shift.id and test_shift.overlaps_with(other)
                        for other in all_shifts
                    )
                    if has_overlap:
                        continue

                    available_count = sum(
                        1 for uid, user in self.users.items()
                        if shifts_worked.get(uid, 0) < user.max_shifts_per_week
                        and user.is_available(day, start_hour, start_minute, end_hour, end_minute)
                    )

                    if available_count >= shift.required_staff and available_count > best_score:
                        best_score = available_count
                        best_slot = (day, start_hour, start_minute, end_hour, end_minute)

        return best_slot


# =============================================================================
# THEME MANAGER
# =============================================================================

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
        'text_secondary': '#aaaaaa',
        'text_muted': '#777777',
        'success': '#3CB371',
        'warning': '#DAA520',
        'danger': '#CD5C5C',
        'button_bg': '#404040',
        'entry_bg': '#3d3d3d',
    }

    def __init__(self, dark_mode: bool = False):
        self.dark_mode = dark_mode

    @property
    def theme(self) -> dict:
        return self.DARK_THEME if self.dark_mode else self.LIGHT_THEME

    def toggle(self) -> None:
        self.dark_mode = not self.dark_mode


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class SchedulerApp:
    """Main application window with all features."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    USER_COLORS = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Multi-Week Scheduler v3")
        self.root.geometry("1700x1000")
        self.root.minsize(1500, 900)

        self.state_manager = SchedulerStateManager()
        self.theme_manager = ThemeManager(self.state_manager.settings.get('dark_mode', False))

        self.current_date = date.today()
        self.current_week_key = SchedulerStateManager.get_week_key(self.current_date)
        self.state_manager.set_current_week(self.current_week_key)

        self.selected_user_id: Optional[str] = None

        self._create_menu()
        self._create_main_layout()
        self._apply_theme()
        self._refresh_all()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_theme(self) -> None:
        theme = self.theme_manager.theme
        self.root.configure(bg=theme['bg'])

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=theme['bg'])
        style.configure('TLabel', background=theme['bg'], foreground=theme['fg'])
        style.configure('TButton', background=theme['button_bg'], foreground=theme['fg'])
        style.map('TButton', background=[('active', theme['accent_hover'])])
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'),
                       background=theme['bg'], foreground=theme['fg'])
        style.configure('TLabelframe', background=theme['bg'], foreground=theme['fg'])
        style.configure('TLabelframe.Label', background=theme['bg'], foreground=theme['fg'])

        if hasattr(self, 'users_listbox'):
            self.users_listbox.configure(
                bg=theme['listbox_bg'], fg=theme['listbox_fg'],
                selectbackground=theme['listbox_select_bg'],
                selectforeground=theme['listbox_select_fg']
            )
        if hasattr(self, 'shifts_listbox'):
            self.shifts_listbox.configure(
                bg=theme['listbox_bg'], fg=theme['listbox_fg'],
                selectbackground=theme['listbox_select_bg'],
                selectforeground=theme['listbox_select_fg']
            )
        if hasattr(self, 'calendar_canvas'):
            self.calendar_canvas.configure(bg=theme['canvas_bg'])
            self._draw_calendar()

    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save All", command=self._save_all)
        file_menu.add_command(label="Load Sample Data", command=self._load_sample_data)
        file_menu.add_separator()
        file_menu.add_command(label="Print Schedule", command=self._print_schedule)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        schedule_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Schedule", menu=schedule_menu)
        schedule_menu.add_command(label="Auto-Schedule All", command=self._auto_schedule)
        schedule_menu.add_command(label="Clear All Assignments", command=self._clear_assignments)
        schedule_menu.add_separator()
        schedule_menu.add_command(label="Clear Current Week", command=self._clear_week)
        schedule_menu.add_separator()
        schedule_menu.add_command(label="Check User Conflicts", command=self._check_user_conflicts)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self.dark_mode_var = tk.BooleanVar(value=self.theme_manager.dark_mode)
        view_menu.add_checkbutton(label="Dark Mode", variable=self.dark_mode_var,
                                 command=self._toggle_dark_mode)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self) -> None:
        theme = self.theme_manager.theme

        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(self.main_frame, width=420)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        self._create_users_panel(left_panel)
        self._create_shifts_panel(left_panel)

        right_panel = ttk.Frame(self.main_frame)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_navigation_panel(right_panel)
        self._create_calendar_panel(right_panel)

    def _create_navigation_panel(self, parent: ttk.Frame) -> None:
        nav_frame = ttk.Frame(parent)
        nav_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(nav_frame, text="◀ Previous Week",
                  command=self._go_previous_week).pack(side=tk.LEFT, padx=5)

        self.week_label = ttk.Label(nav_frame, text="", style='Header.TLabel')
        self.week_label.pack(side=tk.LEFT, padx=20)

        ttk.Button(nav_frame, text="Today",
                  command=self._go_today).pack(side=tk.LEFT, padx=5)

        ttk.Button(nav_frame, text="Next Week ▶",
                  command=self._go_next_week).pack(side=tk.LEFT, padx=5)

        self._update_week_label()

    def _update_week_label(self) -> None:
        week_start = SchedulerStateManager.get_week_start(self.current_date)
        week_end = week_start + timedelta(days=6)
        self.week_label.config(
            text=f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')} ({self.current_week_key})"
        )

    def _go_previous_week(self) -> None:
        self.current_date -= timedelta(days=7)
        self._change_week()

    def _go_next_week(self) -> None:
        self.current_date += timedelta(days=7)
        self._change_week()

    def _go_today(self) -> None:
        self.current_date = date.today()
        self._change_week()

    def _change_week(self) -> None:
        self.current_week_key = SchedulerStateManager.get_week_key(self.current_date)
        self.state_manager.set_current_week(self.current_week_key)
        self._update_week_label()
        self._refresh_all()

    def _create_users_panel(self, parent: ttk.Frame) -> None:
        theme = self.theme_manager.theme

        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(header_frame, text="👤 Users", style='Header.TLabel').pack(side=tk.LEFT)

        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="+", width=3, command=self._add_user).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✎", width=3, command=self._edit_user).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑", width=3, command=self._delete_user).pack(side=tk.LEFT, padx=2)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.users_listbox = tk.Listbox(
            list_frame, font=('Segoe UI', 10), selectmode=tk.SINGLE,
            activestyle='none', highlightthickness=1,
            bg=theme['listbox_bg'], fg=theme['listbox_fg'],
            selectbackground=theme['listbox_select_bg'],
            selectforeground=theme['listbox_select_fg']
        )
        self.users_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.users_listbox.bind('<<ListboxSelect>>', self._on_user_select)
        self.users_listbox.bind('<Double-Button-1>', lambda e: self._edit_user())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.users_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_listbox.config(yscrollcommand=scrollbar.set)

        ttk.Button(parent, text="Manage Conflict Pairs",
                  command=self._manage_conflicts).pack(fill=tk.X, pady=(0, 10))

    def _create_shifts_panel(self, parent: ttk.Frame) -> None:
        theme = self.theme_manager.theme

        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(header_frame, text="📅 Shifts (This Week)", style='Header.TLabel').pack(side=tk.LEFT)

        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="+", width=3, command=self._add_shift).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✎", width=3, command=self._edit_shift).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑", width=3, command=self._delete_shift).pack(side=tk.LEFT, padx=2)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.shifts_listbox = tk.Listbox(
            list_frame, font=('Segoe UI', 10), selectmode=tk.SINGLE,
            activestyle='none', highlightthickness=1,
            bg=theme['listbox_bg'], fg=theme['listbox_fg'],
            selectbackground=theme['listbox_select_bg'],
            selectforeground=theme['listbox_select_fg']
        )
        self.shifts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.shifts_listbox.bind('<Double-Button-1>', lambda e: self._edit_shift())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.shifts_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.shifts_listbox.config(yscrollcommand=scrollbar.set)

        ttk.Button(parent, text="👥 Assign Users to Shift",
                  command=self._manual_assign).pack(fill=tk.X, pady=(0, 5))

        ttk.Button(parent, text="🔄 Auto-Schedule",
                  command=self._auto_schedule).pack(fill=tk.X, pady=(5, 0))

    def _create_calendar_panel(self, parent: ttk.Frame) -> None:
        theme = self.theme_manager.theme

        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(header_frame, text="📆 Weekly Schedule", style='Header.TLabel').pack(side=tk.LEFT)

        legend_frame = ttk.Frame(header_frame)
        legend_frame.pack(side=tk.RIGHT)

        fixed_legend = tk.Canvas(legend_frame, width=15, height=15, highlightthickness=0, bg=theme['bg'])
        fixed_legend.create_rectangle(0, 0, 15, 15, fill=theme['shift_fixed'], outline='')
        fixed_legend.pack(side=tk.LEFT, padx=(10, 2))
        ttk.Label(legend_frame, text="Fixed", font=('Segoe UI', 9)).pack(side=tk.LEFT)

        flex_legend = tk.Canvas(legend_frame, width=15, height=15, highlightthickness=0, bg=theme['bg'])
        flex_legend.create_rectangle(0, 0, 15, 15, fill=theme['shift_flexible'], outline='')
        flex_legend.pack(side=tk.LEFT, padx=(10, 2))
        ttk.Label(legend_frame, text="Flexible", font=('Segoe UI', 9)).pack(side=tk.LEFT)

        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.calendar_canvas = tk.Canvas(
            canvas_frame, bg=theme['canvas_bg'], highlightthickness=1,
            highlightbackground=theme['card_border'], yscrollcommand=v_scroll.set
        )
        self.calendar_canvas.pack(fill=tk.BOTH, expand=True)
        v_scroll.config(command=self.calendar_canvas.yview)

        self.calendar_canvas.bind('<Configure>', self._on_canvas_resize)
        self.calendar_canvas.bind('<MouseWheel>', self._on_canvas_scroll)

    def _group_overlapping_shifts(self, shifts: List[Shift]) -> List[List[Shift]]:
        if not shifts:
            return []

        sorted_shifts = sorted(shifts, key=lambda s: s.start_hour * 60 + s.start_minute)
        groups = []
        current_group = [sorted_shifts[0]]
        group_end = sorted_shifts[0].end_hour * 60 + sorted_shifts[0].end_minute

        for shift in sorted_shifts[1:]:
            shift_start = shift.start_hour * 60 + shift.start_minute
            shift_end = shift.end_hour * 60 + shift.end_minute

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
        self.calendar_canvas.delete('all')
        theme = self.theme_manager.theme

        width = self.calendar_canvas.winfo_width()
        height = max(self.calendar_canvas.winfo_height(), 800)

        if width < 100:
            return

        time_col_width = 60
        header_height = 40
        available_width = width - time_col_width - 30
        day_width = available_width / 7

        hours = list(range(24))
        hour_height = max(30, (height - header_height - 20) / len(hours))
        total_height = header_height + hour_height * len(hours) + 20

        self.calendar_canvas.configure(scrollregion=(0, 0, width, total_height))

        week_start = SchedulerStateManager.get_week_start(self.current_date)
        for i, day in enumerate(self.DAY_ABBREV):
            x = time_col_width + i * day_width + day_width / 2
            day_date = week_start + timedelta(days=i)
            date_str = day_date.strftime('%m/%d')

            if day_date == date.today():
                self.calendar_canvas.create_rectangle(
                    time_col_width + i * day_width, 0,
                    time_col_width + (i + 1) * day_width, header_height,
                    fill='#3D5A80', outline=''
                )

            self.calendar_canvas.create_text(
                x, header_height / 2 - 8, text=day,
                font=('Segoe UI', 11, 'bold'), fill=theme['fg']
            )
            self.calendar_canvas.create_text(
                x, header_height / 2 + 8, text=date_str,
                font=('Segoe UI', 9), fill=theme['text_secondary']
            )

        for i, hour in enumerate(hours):
            y = header_height + i * hour_height + hour_height / 2
            self.calendar_canvas.create_text(
                time_col_width / 2, y, text=f"{hour:02d}:00",
                font=('Segoe UI', 9), fill=theme['text_secondary']
            )

        for i in range(8):
            x = time_col_width + i * day_width
            self.calendar_canvas.create_line(
                x, header_height, x, total_height - 10, fill=theme['grid_line']
            )

        for i in range(len(hours) + 1):
            y = header_height + i * hour_height
            self.calendar_canvas.create_line(
                time_col_width, y, width - 20, y, fill=theme['grid_line']
            )

        week_state = self.state_manager.get_current_week_state()
        if week_state:
            for day in range(7):
                day_shifts = week_state.get_shifts_for_day(day)
                overlap_groups = self._group_overlapping_shifts(day_shifts)
                for group in overlap_groups:
                    total_in_group = len(group)
                    for idx, shift in enumerate(group):
                        self._draw_shift(shift, time_col_width, header_height,
                                        day_width, hour_height, idx, total_in_group)

    def _draw_shift(self, shift: Shift, time_col_width: float, header_height: float,
                    day_width: float, hour_height: float,
                    shift_index: int = 0, total_in_slot: int = 1) -> None:
        theme = self.theme_manager.theme

        start_offset = shift.start_hour + shift.start_minute / 60.0
        end_offset = shift.end_hour + shift.end_minute / 60.0

        slot_width = (day_width - 6) / total_in_slot
        x1 = time_col_width + shift.day * day_width + 3 + (shift_index * slot_width)
        x2 = x1 + slot_width - 2
        y1 = header_height + start_offset * hour_height + 2
        y2 = header_height + end_offset * hour_height - 2

        if shift.shift_type == ShiftType.FIXED:
            color = theme['shift_fixed']
            border_color = theme['shift_fixed_border']
        else:
            color = theme['shift_flexible']
            border_color = theme['shift_flexible_border']

        self.calendar_canvas.create_rectangle(
            x1, y1, x2, y2, fill=color, outline=border_color, width=2
        )

        type_indicator = "📌" if shift.shift_type == ShiftType.FIXED else "🔄"
        title = f"{type_indicator} {shift.name}"

        self.calendar_canvas.create_text(
            (x1 + x2) / 2, y1 + 12, text=title,
            font=('Segoe UI', 8, 'bold'),
            fill='#333333' if not self.theme_manager.dark_mode else '#ffffff',
            width=x2 - x1 - 4
        )

        self.calendar_canvas.create_text(
            (x1 + x2) / 2, y1 + 26, text=shift.time_str(),
            font=('Segoe UI', 7),
            fill='#555555' if not self.theme_manager.dark_mode else '#cccccc'
        )

        if shift.assigned_users:
            user_names = [self.state_manager.users[uid].name
                         for uid in shift.assigned_users
                         if uid in self.state_manager.users]
            assigned_text = ", ".join(user_names[:2])
            if len(user_names) > 2:
                assigned_text += f" +{len(user_names) - 2}"
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 40, text=assigned_text,
                font=('Segoe UI', 7, 'italic'),
                fill='#444444' if not self.theme_manager.dark_mode else '#bbbbbb',
                width=x2 - x1 - 4
            )
        else:
            self.calendar_canvas.create_text(
                (x1 + x2) / 2, y1 + 40, text=f"(need {shift.required_staff})",
                font=('Segoe UI', 7, 'italic'), fill=theme['text_muted']
            )

    def _on_canvas_resize(self, event) -> None:
        self._draw_calendar()

    def _on_canvas_scroll(self, event) -> None:
        self.calendar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _refresh_all(self) -> None:
        self._refresh_users_list()
        self._refresh_shifts_list()
        self._draw_calendar()

    def _refresh_users_list(self) -> None:
        self.users_listbox.delete(0, tk.END)
        week_state = self.state_manager.get_current_week_state()
        shifts = week_state.get_all_shifts() if week_state else []

        for user_id, user in sorted(self.state_manager.users.items(), key=lambda x: x[1].name):
            shift_count = sum(1 for s in shifts if user_id in s.assigned_users)
            display = f"  {user.name} - {shift_count} shifts (max: {user.max_shifts_per_week})"
            self.users_listbox.insert(tk.END, display)

    def _refresh_shifts_list(self) -> None:
        self.shifts_listbox.delete(0, tk.END)
        week_state = self.state_manager.get_current_week_state()
        if not week_state:
            return

        for shift in sorted(week_state.get_all_shifts(),
                           key=lambda s: (s.day, s.start_hour, s.start_minute)):
            type_icon = "📌" if shift.shift_type == ShiftType.FIXED else "🔄"
            day_abbrev = self.DAY_ABBREV[shift.day]
            assigned_count = len(shift.assigned_users)
            display = f"{type_icon} {shift.name} - {day_abbrev} {shift.time_str()} [{assigned_count}/{shift.required_staff}]"
            self.shifts_listbox.insert(tk.END, display)

    def _on_user_select(self, event) -> None:
        selection = self.users_listbox.curselection()
        if selection:
            index = selection[0]
            user_ids = sorted(self.state_manager.users.keys(),
                            key=lambda uid: self.state_manager.users[uid].name)
            if index < len(user_ids):
                self.selected_user_id = user_ids[index]

    def _get_selected_shift(self) -> Optional[Shift]:
        selection = self.shifts_listbox.curselection()
        if not selection:
            return None
        week_state = self.state_manager.get_current_week_state()
        if not week_state:
            return None
        shifts = sorted(week_state.get_all_shifts(),
                       key=lambda s: (s.day, s.start_hour, s.start_minute))
        index = selection[0]
        if index < len(shifts):
            return shifts[index]
        return None

    # ========================================================================
    # User Management
    # ========================================================================

    def _add_user(self) -> None:
        dialog = UserDialog(self.root, "Add User", self.USER_COLORS, self.theme_manager)
        if dialog.result:
            self.state_manager.add_user(
                name=dialog.result['name'],
                max_shifts=dialog.result['max_shifts'],
                color=dialog.result['color'],
                availability=dialog.result['availability']
            )
            self._save_all()
            self._refresh_all()

    def _edit_user(self) -> None:
        selection = self.users_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a user to edit.")
            return

        index = selection[0]
        user_ids = sorted(self.state_manager.users.keys(),
                         key=lambda uid: self.state_manager.users[uid].name)
        if index >= len(user_ids):
            return

        user_id = user_ids[index]
        user = self.state_manager.users[user_id]

        dialog = UserDialog(self.root, "Edit User", self.USER_COLORS, self.theme_manager, user)
        if dialog.result:
            user.name = dialog.result['name']
            user.max_shifts_per_week = dialog.result['max_shifts']
            user.color = dialog.result['color']
            user.availability = dialog.result['availability']
            self._save_all()
            self._refresh_all()

    def _delete_user(self) -> None:
        selection = self.users_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a user to delete.")
            return

        index = selection[0]
        user_ids = sorted(self.state_manager.users.keys(),
                         key=lambda uid: self.state_manager.users[uid].name)
        if index >= len(user_ids):
            return

        user_id = user_ids[index]
        user = self.state_manager.users[user_id]

        if messagebox.askyesno("Confirm Delete", f"Delete user '{user.name}'?"):
            self.state_manager.remove_user(user_id)
            self._save_all()
            self._refresh_all()

    def _manage_conflicts(self) -> None:
        dialog = ConflictDialog(self.root, self.state_manager.users,
                               self.state_manager.conflicts, self.theme_manager)
        if dialog.result is not None:
            self.state_manager.conflicts = dialog.result
            self._save_all()

    # ========================================================================
    # Shift Management
    # ========================================================================

    def _add_shift(self) -> None:
        dialog = ShiftDialog(self.root, "Add Shift", self.state_manager.users, self.theme_manager)
        if dialog.result:
            self.state_manager.add_shift(
                week_key=self.current_week_key,
                name=dialog.result['name'],
                shift_type=dialog.result['shift_type'],
                day=dialog.result['day'],
                start_hour=dialog.result['start_hour'],
                start_minute=dialog.result['start_minute'],
                end_hour=dialog.result['end_hour'],
                end_minute=dialog.result['end_minute'],
                required_staff=dialog.result['required_staff']
            )
            self._save_all()
            self._refresh_all()

    def _edit_shift(self) -> None:
        shift = self._get_selected_shift()
        if not shift:
            messagebox.showwarning("Warning", "Please select a shift to edit.")
            return

        dialog = ShiftDialog(self.root, "Edit Shift", self.state_manager.users,
                            self.theme_manager, shift)
        if dialog.result:
            shift.name = dialog.result['name']
            shift.shift_type = dialog.result['shift_type']
            shift.day = dialog.result['day']
            shift.start_hour = dialog.result['start_hour']
            shift.start_minute = dialog.result['start_minute']
            shift.end_hour = dialog.result['end_hour']
            shift.end_minute = dialog.result['end_minute']
            shift.required_staff = dialog.result['required_staff']

            week_state = self.state_manager.get_current_week_state()
            if week_state:
                week_state.is_dirty = True

            self._save_all()
            self._refresh_all()

    def _delete_shift(self) -> None:
        shift = self._get_selected_shift()
        if not shift:
            messagebox.showwarning("Warning", "Please select a shift to delete.")
            return

        if messagebox.askyesno("Confirm Delete", f"Delete shift '{shift.name}'?"):
            self.state_manager.remove_shift(self.current_week_key, shift.id)
            self._save_all()
            self._refresh_all()

    def _manual_assign(self) -> None:
        shift = self._get_selected_shift()
        if not shift:
            messagebox.showwarning("Warning", "Please select a shift to assign users.")
            return

        week_state = self.state_manager.get_current_week_state()
        all_shifts = week_state.get_all_shifts() if week_state else []

        dialog = AssignUsersDialog(
            self.root, shift, self.state_manager.users, all_shifts,
            self.state_manager.conflicts, self.theme_manager
        )
        if dialog.result is not None:
            shift.assigned_users = dialog.result
            if week_state:
                week_state.is_dirty = True
            self._save_all()
            self._refresh_all()

    # ========================================================================
    # Scheduling
    # ========================================================================

    def _auto_schedule(self) -> None:
        if not self.state_manager.users:
            messagebox.showwarning("Warning", "No users to schedule!")
            return

        week_state = self.state_manager.get_current_week_state()
        if not week_state or not week_state.shifts:
            messagebox.showwarning("Warning", "No shifts to schedule!")
            return

        scheduler = Scheduler(self.state_manager.users, self.state_manager.conflicts)
        shifts = list(week_state.shifts.values())
        scheduled = scheduler.schedule_shifts(shifts)

        for shift in scheduled:
            week_state.shifts[shift.id] = shift
        week_state.is_dirty = True

        self._save_all()
        self._refresh_all()

        distribution = {}
        for user_id, user in self.state_manager.users.items():
            count = sum(1 for s in scheduled if user_id in s.assigned_users)
            distribution[user.name] = count

        summary = "Shift Distribution:\n\n"
        for name, count in sorted(distribution.items()):
            user = next((u for u in self.state_manager.users.values() if u.name == name), None)
            max_shifts = user.max_shifts_per_week if user else 5
            summary += f"  {name}: {count} shifts (max: {max_shifts})\n"
        messagebox.showinfo("Auto-Schedule Complete", summary)

    def _clear_assignments(self) -> None:
        if messagebox.askyesno("Confirm", "Clear all shift assignments for this week?"):
            week_state = self.state_manager.get_current_week_state()
            if week_state:
                for shift in week_state.shifts.values():
                    shift.assigned_users = []
                week_state.is_dirty = True
            self._save_all()
            self._refresh_all()

    def _clear_week(self) -> None:
        week_state = self.state_manager.get_current_week_state()
        if not week_state or not week_state.shifts:
            messagebox.showinfo("Clear Week", "No shifts to clear.")
            return

        count = len(week_state.shifts)
        if messagebox.askyesno(
            "Clear Week",
            f"Are you sure you want to clear all {count} shift(s) from week {self.current_week_key}?\n\n"
            "This will NOT affect users or other weeks."
        ):
            self.state_manager.clear_week(self.current_week_key)
            self._save_all()
            self._refresh_all()
            messagebox.showinfo("Success", f"Cleared {count} shift(s)")

    def _check_user_conflicts(self) -> None:
        week_state = self.state_manager.get_current_week_state()
        if not week_state:
            return

        conflicts_found = []
        shifts = week_state.get_all_shifts()

        for user_id in self.state_manager.users:
            user_shifts = [s for s in shifts if user_id in s.assigned_users]
            for i, s1 in enumerate(user_shifts):
                for s2 in user_shifts[i + 1:]:
                    if s1.overlaps_with(s2):
                        user = self.state_manager.users[user_id]
                        conflicts_found.append((user.name, s1, s2))

        if not conflicts_found:
            messagebox.showinfo("No Conflicts", "No users are double-booked on overlapping shifts!")
        else:
            msg = "The following users have overlapping assignments:\n\n"
            for user_name, s1, s2 in conflicts_found:
                msg += f"• {user_name}:\n"
                msg += f"  {s1.name} ({self.DAY_ABBREV[s1.day]} {s1.time_str()})\n"
                msg += f"  {s2.name} ({self.DAY_ABBREV[s2.day]} {s2.time_str()})\n\n"
            messagebox.showwarning("User Conflicts Found", msg)

    # ========================================================================
    # File Operations
    # ========================================================================

    def _save_all(self) -> None:
        self.state_manager.settings['dark_mode'] = self.theme_manager.dark_mode
        self.state_manager.save_all()

    def _load_sample_data(self) -> None:
        if self.state_manager.users or (self.state_manager.get_current_week_state() and
                                        self.state_manager.get_current_week_state().shifts):
            if not messagebox.askyesno("Confirm", "This will replace existing data. Continue?"):
                return

        self.state_manager.users.clear()
        sample_users = [
            ('Alice', 4, '#FF6B6B', {
                0: [], 1: [TimeRange(9, 0, 17, 0)], 2: [TimeRange(9, 0, 17, 0)],
                3: [TimeRange(9, 0, 17, 0)], 4: [TimeRange(9, 0, 17, 0)],
                5: [TimeRange(10, 0, 14, 0)], 6: []
            }),
            ('Bob', 5, '#4ECDC4', {
                0: [TimeRange(8, 0, 20, 0)], 1: [TimeRange(8, 0, 20, 0)],
                2: [TimeRange(8, 0, 20, 0)], 3: [TimeRange(8, 0, 20, 0)],
                4: [TimeRange(8, 0, 20, 0)], 5: [], 6: []
            }),
            ('Charlie', 3, '#45B7D1', {
                0: [TimeRange(6, 0, 14, 0)], 1: [TimeRange(6, 0, 14, 0)],
                2: [TimeRange(6, 0, 14, 0)], 3: [TimeRange(6, 0, 14, 0)],
                4: [], 5: [TimeRange(8, 0, 16, 0)], 6: [TimeRange(8, 0, 16, 0)]
            }),
            ('Diana', 4, '#96CEB4', {}),
            ('Eve', 5, '#FFEAA7', {
                0: [TimeRange(12, 0, 22, 0)], 1: [TimeRange(12, 0, 22, 0)],
                2: [TimeRange(12, 0, 22, 0)], 3: [TimeRange(12, 0, 22, 0)],
                4: [TimeRange(12, 0, 22, 0)], 5: [TimeRange(10, 0, 22, 0)],
                6: [TimeRange(10, 0, 22, 0)]
            }),
        ]

        for name, max_shifts, color, availability in sample_users:
            self.state_manager.add_user(name, max_shifts, color, availability)

        week_state = self.state_manager.get_current_week_state()
        if week_state:
            week_state.shifts.clear()

        sample_shifts = [
            ('Morning Reception', ShiftType.FIXED, 0, 9, 0, 12, 30, 2),
            ('Afternoon Support', ShiftType.FIXED, 0, 13, 0, 17, 0, 2),
            ('Team Meeting', ShiftType.FLEXIBLE, 2, 10, 0, 12, 0, 3),
            ('Training Session', ShiftType.FLEXIBLE, 3, 14, 30, 16, 30, 2),
            ('Weekly Review', ShiftType.FIXED, 4, 15, 0, 17, 0, 2),
            ('Evening Shift', ShiftType.FIXED, 1, 18, 0, 22, 0, 2),
        ]

        for name, shift_type, day, sh, sm, eh, em, staff in sample_shifts:
            self.state_manager.add_shift(
                self.current_week_key, name, shift_type, day, sh, sm, eh, em, staff
            )

        user_ids = list(self.state_manager.users.keys())
        if len(user_ids) >= 2:
            self.state_manager.conflicts = [(user_ids[0], user_ids[1])]

        self._save_all()
        self._refresh_all()
        messagebox.showinfo("Success", "Sample data loaded!")

    def _print_schedule(self) -> None:
        PrintDialog(self.root, self.state_manager, self.current_week_key, self.theme_manager)

    def _toggle_dark_mode(self) -> None:
        self.theme_manager.toggle()
        self.state_manager.settings['dark_mode'] = self.theme_manager.dark_mode
        self._save_all()
        self._apply_theme()

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About Multi-Week Scheduler",
            "Multi-Week Scheduler v3.0\n\n"
            "Features:\n"
            "• Multi-week scheduling with week navigation\n"
            "• User profile management with availability\n"
            "• Fixed and flexible shift types\n"
            "• Minute-level time precision\n"
            "• Load-balanced auto-scheduling\n"
            "• Conflict pair management\n"
            "• Dark mode support\n"
            "• Print/export functionality\n"
            "• Overlapping shifts displayed side-by-side\n"
            "• No double-booking enforcement\n\n"
            "© 2026 AutoSchedule"
        )

    def _on_close(self) -> None:
        has_unsaved = any(state.is_dirty for state in self.state_manager._week_states.values())
        if has_unsaved:
            if messagebox.askyesno("Unsaved Changes", "Save changes before closing?"):
                self._save_all()
        self.root.destroy()


# =============================================================================
# DIALOGS
# =============================================================================

class UserDialog:
    """Dialog for adding/editing users."""

    DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __init__(self, parent: tk.Tk, title: str, colors: List[str],
                 theme_manager: ThemeManager, user: User = None):
        self.result = None
        self.colors = colors
        self.user = user
        self.theme = theme_manager.theme
        self.availability: Dict[int, List[TimeRange]] = {}

        if user:
            for day in range(7):
                self.availability[day] = list(user.availability.get(day, []))
        else:
            for day in range(7):
                self.availability[day] = [TimeRange(0, 0, 24, 0)]

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("850x700")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(750, 600)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 850) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 700) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(info_frame, text="Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=self.user.name if self.user else "")
        ttk.Entry(info_frame, textvariable=self.name_var, width=20).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(info_frame, text="Max Shifts/Week:").pack(side=tk.LEFT)
        self.max_shifts_var = tk.IntVar(value=self.user.max_shifts_per_week if self.user else 5)
        ttk.Spinbox(info_frame, from_=1, to=21, textvariable=self.max_shifts_var, width=5).pack(side=tk.LEFT, padx=5)

        ttk.Label(info_frame, text="Color:").pack(side=tk.LEFT, padx=(20, 5))
        self.color_var = tk.StringVar(value=self.user.color if self.user else self.colors[0])
        ttk.Combobox(info_frame, textvariable=self.color_var, values=self.colors,
                    width=10, state='readonly').pack(side=tk.LEFT)

        ttk.Label(main_frame, text="Availability (add time ranges for each day):",
                 font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0, 10))

        avail_container = ttk.Frame(main_frame)
        avail_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(avail_container, bg=self.theme['card_bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(avail_container, orient=tk.VERTICAL, command=canvas.yview)
        self.avail_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas_frame = canvas.create_window((0, 0), window=self.avail_frame, anchor=tk.NW)

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_frame, width=event.width - 20)

        canvas.bind('<Configure>', configure_scroll)

        self.range_listboxes = {}

        for day_idx, day_name in enumerate(self.DAYS):
            day_frame = ttk.LabelFrame(self.avail_frame, text=f"  {day_name}  ", padding=5)
            day_frame.pack(fill=tk.X, pady=3, padx=5)

            list_frame = ttk.Frame(day_frame)
            list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lb = tk.Listbox(list_frame, height=2, font=('Segoe UI', 9),
                           bg=self.theme['listbox_bg'], fg=self.theme['listbox_fg'],
                           selectbackground=self.theme['listbox_select_bg'])
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.range_listboxes[day_idx] = lb
            self._refresh_day_ranges(day_idx)

            btn_frame = ttk.Frame(day_frame)
            btn_frame.pack(side=tk.RIGHT, padx=(10, 0))

            ttk.Button(btn_frame, text="+ Add", width=8,
                      command=lambda d=day_idx: self._add_range(d)).pack(pady=1)
            ttk.Button(btn_frame, text="- Remove", width=8,
                      command=lambda d=day_idx: self._remove_range(d)).pack(pady=1)
            ttk.Button(btn_frame, text="All Day", width=8,
                      command=lambda d=day_idx: self._set_all_day(d)).pack(pady=1)
            ttk.Button(btn_frame, text="Clear", width=8,
                      command=lambda d=day_idx: self._clear_day(d)).pack(pady=1)

        quick_frame = ttk.Frame(main_frame)
        quick_frame.pack(fill=tk.X, pady=10)

        ttk.Button(quick_frame, text="All Days Available", command=self._select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="Clear All", command=self._clear_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="Weekdays 9-5", command=self._weekdays_business).pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _refresh_day_ranges(self, day: int) -> None:
        lb = self.range_listboxes[day]
        lb.delete(0, tk.END)
        for tr in self.availability[day]:
            lb.insert(tk.END, f"  {tr}")

    def _add_range(self, day: int) -> None:
        dialog = TimeRangeDialog(self.dialog, self.theme)
        if dialog.result:
            new_range = TimeRange(
                dialog.result['start_hour'], dialog.result['start_minute'],
                dialog.result['end_hour'], dialog.result['end_minute']
            )
            self.availability[day].append(new_range)
            self._refresh_day_ranges(day)

    def _remove_range(self, day: int) -> None:
        lb = self.range_listboxes[day]
        selection = lb.curselection()
        if selection:
            self.availability[day].pop(selection[0])
            self._refresh_day_ranges(day)

    def _set_all_day(self, day: int) -> None:
        self.availability[day] = [TimeRange(0, 0, 24, 0)]
        self._refresh_day_ranges(day)

    def _clear_day(self, day: int) -> None:
        self.availability[day] = []
        self._refresh_day_ranges(day)

    def _select_all(self) -> None:
        for day in range(7):
            self.availability[day] = [TimeRange(0, 0, 24, 0)]
            self._refresh_day_ranges(day)

    def _clear_all(self) -> None:
        for day in range(7):
            self.availability[day] = []
            self._refresh_day_ranges(day)

    def _weekdays_business(self) -> None:
        for day in range(7):
            if day < 5:
                self.availability[day] = [TimeRange(9, 0, 17, 0)]
            else:
                self.availability[day] = []
            self._refresh_day_ranges(day)

    def _save(self) -> None:
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
        self.result = None
        self.theme = theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Add Time Range")
        self.dialog.geometry("400x250")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(350, 200)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 250) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        start_frame = ttk.Frame(main_frame)
        start_frame.pack(fill=tk.X, pady=10)

        ttk.Label(start_frame, text="Start Time:", width=12).pack(side=tk.LEFT)
        self.start_hour_var = tk.IntVar(value=9)
        ttk.Spinbox(start_frame, from_=0, to=23, textvariable=self.start_hour_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT, padx=2)
        ttk.Label(start_frame, text=":").pack(side=tk.LEFT)
        self.start_min_var = tk.IntVar(value=0)
        ttk.Spinbox(start_frame, from_=0, to=59, textvariable=self.start_min_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT, padx=2)

        end_frame = ttk.Frame(main_frame)
        end_frame.pack(fill=tk.X, pady=10)

        ttk.Label(end_frame, text="End Time:", width=12).pack(side=tk.LEFT)
        self.end_hour_var = tk.IntVar(value=17)
        ttk.Spinbox(end_frame, from_=0, to=24, textvariable=self.end_hour_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT, padx=2)
        ttk.Label(end_frame, text=":").pack(side=tk.LEFT)
        self.end_min_var = tk.IntVar(value=0)
        ttk.Spinbox(end_frame, from_=0, to=59, textvariable=self.end_min_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT, padx=2)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(30, 0))

        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Add", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        start_h = self.start_hour_var.get()
        start_m = self.start_min_var.get()
        end_h = self.end_hour_var.get()
        end_m = self.end_min_var.get()

        if end_h * 60 + end_m <= start_h * 60 + start_m:
            messagebox.showerror("Error", "End time must be after start time!")
            return

        self.result = {
            'start_hour': start_h, 'start_minute': start_m,
            'end_hour': end_h, 'end_minute': end_m
        }
        self.dialog.destroy()


class ShiftDialog:
    """Dialog for adding/editing shifts."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, parent: tk.Tk, title: str, users: Dict[str, User],
                 theme_manager: ThemeManager, shift: Shift = None):
        self.result = None
        self.users = users
        self.shift = shift
        self.theme = theme_manager.theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("550x520")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(500, 450)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 550) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="25")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Shift Name:").grid(row=0, column=0, sticky=tk.W, pady=10)
        self.name_var = tk.StringVar(value=self.shift.name if self.shift else "")
        ttk.Entry(main_frame, textvariable=self.name_var, width=35).grid(
            row=0, column=1, columnspan=3, sticky=tk.W, pady=10
        )

        ttk.Label(main_frame, text="Shift Type:").grid(row=1, column=0, sticky=tk.W, pady=10)
        self.type_var = tk.StringVar(value=self.shift.shift_type.value if self.shift else "fixed")
        type_frame = ttk.Frame(main_frame)
        type_frame.grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=10)
        ttk.Radiobutton(type_frame, text="📌 Fixed", variable=self.type_var, value="fixed").pack(side=tk.LEFT)
        ttk.Radiobutton(type_frame, text="🔄 Flexible", variable=self.type_var, value="flexible").pack(side=tk.LEFT, padx=(15, 0))

        ttk.Label(main_frame, text="Day:").grid(row=2, column=0, sticky=tk.W, pady=10)
        self.day_var = tk.StringVar(value=self.DAYS[self.shift.day] if self.shift else self.DAYS[0])
        ttk.Combobox(main_frame, textvariable=self.day_var, values=self.DAYS,
                    state='readonly', width=18).grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=10)

        ttk.Label(main_frame, text="Start Time:").grid(row=3, column=0, sticky=tk.W, pady=10)
        start_frame = ttk.Frame(main_frame)
        start_frame.grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=10)

        self.start_hour_var = tk.IntVar(value=self.shift.start_hour if self.shift else 9)
        ttk.Spinbox(start_frame, from_=0, to=23, textvariable=self.start_hour_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT)
        ttk.Label(start_frame, text=":").pack(side=tk.LEFT)
        self.start_min_var = tk.IntVar(value=self.shift.start_minute if self.shift else 0)
        ttk.Spinbox(start_frame, from_=0, to=59, textvariable=self.start_min_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT)

        ttk.Label(main_frame, text="End Time:").grid(row=4, column=0, sticky=tk.W, pady=10)
        end_frame = ttk.Frame(main_frame)
        end_frame.grid(row=4, column=1, columnspan=3, sticky=tk.W, pady=10)

        self.end_hour_var = tk.IntVar(value=self.shift.end_hour if self.shift else 17)
        ttk.Spinbox(end_frame, from_=0, to=24, textvariable=self.end_hour_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT)
        ttk.Label(end_frame, text=":").pack(side=tk.LEFT)
        self.end_min_var = tk.IntVar(value=self.shift.end_minute if self.shift else 0)
        ttk.Spinbox(end_frame, from_=0, to=59, textvariable=self.end_min_var,
                   width=5, format="%02.0f").pack(side=tk.LEFT)

        ttk.Label(main_frame, text="Required Staff:").grid(row=5, column=0, sticky=tk.W, pady=10)
        self.staff_var = tk.IntVar(value=self.shift.required_staff if self.shift else 2)
        ttk.Spinbox(main_frame, from_=1, to=20, textvariable=self.staff_var, width=5).grid(
            row=5, column=1, sticky=tk.W, pady=10
        )

        note_label = ttk.Label(
            main_frame,
            text="Note: Flexible shifts may be moved to optimal\ntimes during auto-scheduling.",
            font=('Segoe UI', 9, 'italic'),
            foreground=self.theme['text_secondary']
        )
        note_label.grid(row=6, column=0, columnspan=4, pady=25)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=4, pady=(15, 0))

        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Shift name is required!")
            return

        start_h = self.start_hour_var.get()
        start_m = self.start_min_var.get()
        end_h = self.end_hour_var.get()
        end_m = self.end_min_var.get()

        if end_h * 60 + end_m <= start_h * 60 + start_m:
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

    def __init__(self, parent: tk.Tk, shift: Shift, users: Dict[str, User],
                 all_shifts: List[Shift], conflicts: List[Tuple[str, str]],
                 theme_manager: ThemeManager):
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
        self.dialog.geometry("600x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(500, 450)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 600) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _check_user_overlap(self, user_id: str) -> bool:
        for other_shift in self.all_shifts:
            if other_shift.id == self.shift.id:
                continue
            if user_id in other_shift.assigned_users:
                if self.shift.overlaps_with(other_shift):
                    return True
        return False

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        info_text = (
            f"Shift: {self.shift.name}\n"
            f"Day: {day_names[self.shift.day]}\n"
            f"Time: {self.shift.time_str()}\n"
            f"Required: {self.shift.required_staff} staff"
        )
        ttk.Label(main_frame, text=info_text, font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 15))

        ttk.Label(main_frame, text="Select users to assign:",
                 font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)

        self.user_vars: Dict[str, tk.BooleanVar] = {}

        users_frame = ttk.Frame(main_frame)
        users_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        canvas = tk.Canvas(users_frame, bg=self.theme['card_bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(users_frame, orient=tk.VERTICAL, command=canvas.yview)
        inner_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.create_window((0, 0), window=inner_frame, anchor=tk.NW)

        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind('<Configure>', configure_scroll)

        for user_id, user in sorted(self.users.items(), key=lambda x: x[1].name):
            var = tk.BooleanVar(value=user_id in self.shift.assigned_users)
            self.user_vars[user_id] = var

            frame = ttk.Frame(inner_frame)
            frame.pack(fill=tk.X, pady=2)

            cb = ttk.Checkbutton(frame, text=user.name, variable=var)
            cb.pack(side=tk.LEFT)

            available = user.is_available(
                self.shift.day, self.shift.start_hour, self.shift.start_minute,
                self.shift.end_hour, self.shift.end_minute
            )
            has_overlap = self._check_user_overlap(user_id)

            status_parts = []
            if not available:
                status_parts.append("❌ unavailable")
            if has_overlap:
                status_parts.append("⚠️ overlap")

            if status_parts:
                ttk.Label(frame, text=f"({', '.join(status_parts)})",
                         foreground=self.theme['danger'], font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=10)
            else:
                ttk.Label(frame, text="✓ available",
                         foreground=self.theme['success'], font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=10)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Assign", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _save(self) -> None:
        assigned = [uid for uid, var in self.user_vars.items() if var.get()]

        for i, u1 in enumerate(assigned):
            for u2 in assigned[i + 1:]:
                if (u1, u2) in self.conflicts:
                    n1 = self.users[u1].name
                    n2 = self.users[u2].name
                    messagebox.showerror("Conflict", f"{n1} and {n2} have a conflict.")
                    return

        overlapping = [uid for uid in assigned if self._check_user_overlap(uid)]
        if overlapping:
            names = [self.users[uid].name for uid in overlapping]
            if not messagebox.askyesno("Warning",
                                       f"The following users have overlapping shifts: {', '.join(names)}\n\nAssign anyway?"):
                return

        self.result = assigned
        self.dialog.destroy()


class ConflictDialog:
    """Dialog for managing conflict pairs."""

    def __init__(self, parent: tk.Tk, users: Dict[str, User],
                 conflicts: List[Tuple[str, str]], theme_manager: ThemeManager):
        self.result = None
        self.users = users
        self.conflicts = list(conflicts)
        self.theme = theme_manager.theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Manage Conflict Pairs")
        self.dialog.geometry("550x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg=self.theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(450, 400)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 550) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 500) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()
        parent.wait_window(self.dialog)

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Users in conflict pairs cannot be scheduled together.",
                 font=('Segoe UI', 9, 'italic'),
                 foreground=self.theme['text_secondary']).pack(anchor=tk.W, pady=(0, 10))

        add_frame = ttk.LabelFrame(main_frame, text="Add Conflict Pair", padding=10)
        add_frame.pack(fill=tk.X, pady=(0, 10))

        user_names = [(uid, u.name) for uid, u in sorted(self.users.items(), key=lambda x: x[1].name)]

        ttk.Label(add_frame, text="User 1:").grid(row=0, column=0, padx=5)
        self.user1_var = tk.StringVar()
        user1_combo = ttk.Combobox(add_frame, textvariable=self.user1_var,
                                  values=[f"{name} ({uid})" for uid, name in user_names],
                                  state='readonly', width=18)
        user1_combo.grid(row=0, column=1, padx=5)

        ttk.Label(add_frame, text="User 2:").grid(row=0, column=2, padx=5)
        self.user2_var = tk.StringVar()
        user2_combo = ttk.Combobox(add_frame, textvariable=self.user2_var,
                                  values=[f"{name} ({uid})" for uid, name in user_names],
                                  state='readonly', width=18)
        user2_combo.grid(row=0, column=3, padx=5)

        ttk.Button(add_frame, text="Add", command=self._add_conflict).grid(row=0, column=4, padx=10)

        ttk.Label(main_frame, text="Existing Conflicts:").pack(anchor=tk.W)

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.conflicts_listbox = tk.Listbox(
            list_frame, font=('Segoe UI', 10),
            bg=self.theme['listbox_bg'], fg=self.theme['listbox_fg'],
            selectbackground=self.theme['listbox_select_bg']
        )
        self.conflicts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.conflicts_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conflicts_listbox.config(yscrollcommand=scrollbar.set)

        self._refresh_list()

        ttk.Button(main_frame, text="Remove Selected", command=self._remove_conflict).pack(anchor=tk.W, pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)

    def _refresh_list(self) -> None:
        self.conflicts_listbox.delete(0, tk.END)
        for uid1, uid2 in self.conflicts:
            name1 = self.users[uid1].name if uid1 in self.users else uid1
            name2 = self.users[uid2].name if uid2 in self.users else uid2
            self.conflicts_listbox.insert(tk.END, f"  {name1}  ↔  {name2}")

    def _add_conflict(self) -> None:
        sel1 = self.user1_var.get()
        sel2 = self.user2_var.get()

        if not sel1 or not sel2:
            messagebox.showerror("Error", "Please select both users!")
            return

        uid1 = sel1.split('(')[-1].rstrip(')')
        uid2 = sel2.split('(')[-1].rstrip(')')

        if uid1 == uid2:
            messagebox.showerror("Error", "Cannot conflict with self!")
            return

        for c1, c2 in self.conflicts:
            if (c1 == uid1 and c2 == uid2) or (c1 == uid2 and c2 == uid1):
                messagebox.showwarning("Warning", "Conflict pair already exists!")
                return

        self.conflicts.append((uid1, uid2))
        self._refresh_list()

    def _remove_conflict(self) -> None:
        selection = self.conflicts_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a conflict to remove.")
            return
        self.conflicts.pop(selection[0])
        self._refresh_list()

    def _cancel(self) -> None:
        self.result = None
        self.dialog.destroy()

    def _save(self) -> None:
        self.result = self.conflicts
        self.dialog.destroy()


class PrintDialog:
    """Dialog for printing/exporting the schedule."""

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, parent: tk.Tk, state_manager: SchedulerStateManager,
                 week_key: str, theme_manager: ThemeManager):
        self.state_manager = state_manager
        self.week_key = week_key
        self.theme = theme_manager.theme

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Print Schedule")
        self.dialog.geometry("900x700")
        self.dialog.transient(parent)
        self.dialog.configure(bg=self.theme['bg'])
        self.dialog.resizable(True, True)
        self.dialog.minsize(750, 550)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 900) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 700) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self) -> None:
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Schedule Preview",
                 font=('Segoe UI', 14, 'bold')).pack(anchor=tk.W, pady=(0, 10))

        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text_widget = tk.Text(text_frame, font=('Consolas', 10),
                                  bg='white', fg='black', wrap=tk.NONE)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_widget.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        x_scroll = ttk.Scrollbar(main_frame, orient=tk.HORIZONTAL, command=self.text_widget.xview)
        x_scroll.pack(fill=tk.X)

        self.text_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self._generate_content()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Close", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Copy to Clipboard", command=self._copy_to_clipboard).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save as Text File", command=self._save_to_file).pack(side=tk.RIGHT, padx=5)

    def _generate_content(self) -> None:
        week_state = self.state_manager.get_or_create_week_state(self.week_key)
        shifts = week_state.get_all_shifts()

        lines = []
        lines.append("=" * 80)
        lines.append("                        WEEKLY SCHEDULE")
        lines.append(f"                Week: {self.week_key}")
        lines.append(f"                Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 80)
        lines.append("")

        for day_idx, day_name in enumerate(self.DAYS):
            day_shifts = [s for s in shifts if s.day == day_idx]
            day_shifts.sort(key=lambda s: s.start_hour * 60 + s.start_minute)

            lines.append(f"┌{'─' * 78}┐")
            lines.append(f"│ {day_name.upper():^76} │")
            lines.append(f"├{'─' * 78}┤")

            if not day_shifts:
                lines.append(f"│ {'No shifts scheduled':^76} │")
            else:
                for shift in day_shifts:
                    type_str = "FIXED" if shift.shift_type == ShiftType.FIXED else "FLEX"
                    user_names = [self.state_manager.users[uid].name
                                 for uid in shift.assigned_users
                                 if uid in self.state_manager.users]
                    assigned = ", ".join(user_names) or "(unassigned)"

                    line1 = f"  [{type_str}] {shift.name}"
                    line2 = f"          Time: {shift.time_str()}  |  Staff: {assigned}"

                    lines.append(f"│ {line1:<76} │")
                    lines.append(f"│ {line2:<76} │")
                    lines.append(f"│ {' ' * 76} │")

            lines.append(f"└{'─' * 78}┘")
            lines.append("")

        lines.append("=" * 80)
        lines.append("                        STAFF SUMMARY")
        lines.append("=" * 80)
        lines.append("")

        for user_id, user in sorted(self.state_manager.users.items(), key=lambda x: x[1].name):
            shift_count = sum(1 for s in shifts if user_id in s.assigned_users)
            lines.append(f"  {user.name}: {shift_count} shifts (max: {user.max_shifts_per_week})")

        lines.append("")
        lines.append("=" * 80)

        self.text_widget.insert('1.0', '\n'.join(lines))
        self.text_widget.configure(state='disabled')

    def _copy_to_clipboard(self) -> None:
        self.text_widget.configure(state='normal')
        content = self.text_widget.get('1.0', tk.END)
        self.text_widget.configure(state='disabled')
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(content)
        messagebox.showinfo("Copied", "Schedule copied to clipboard!")

    def _save_to_file(self) -> None:
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfilename=f"schedule_{self.week_key}.txt"
        )

        if filename:
            self.text_widget.configure(state='normal')
            content = self.text_widget.get('1.0', tk.END)
            self.text_widget.configure(state='disabled')
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Schedule saved to:\n{filename}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Application entry point."""
    root = tk.Tk()
    app = SchedulerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
