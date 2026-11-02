"""Mouse control through Quartz events. All coordinates are screen points."""

import threading
import time

import AppKit
import Quartz

STOP_CORNER_SIZE = 5
STEP_DELAY = 0.04
DRAG_STEPS = 12
NORMAL_WINDOW_LAYER = 0


_stop_pressed = threading.Event()


class StopRequested(Exception):
    """You pressed Stop, or pushed the mouse into the top-left screen corner."""


def has_accessibility():
    return bool(Quartz.CGPreflightPostEventAccess())


def request_accessibility():
    """Ask macOS to list this app under Accessibility in System Settings."""
    Quartz.CGRequestPostEventAccess()


def position():
    point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return point.x, point.y


def press_stop():
    _stop_pressed.set()


def clear_stop():
    _stop_pressed.clear()


def check_stop():
    if _stop_pressed.is_set():
        raise StopRequested
    x, y = position()
    if x <= STOP_CORNER_SIZE and y <= STOP_CORNER_SIZE:
        raise StopRequested


def _post(kind, x, y):
    event = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def move_to(x, y):
    check_stop()
    _post(Quartz.kCGEventMouseMoved, x, y)
    time.sleep(STEP_DELAY)


def click(x, y):
    move_to(x, y)
    _post(Quartz.kCGEventLeftMouseDown, x, y)
    time.sleep(STEP_DELAY)
    _post(Quartz.kCGEventLeftMouseUp, x, y)
    time.sleep(STEP_DELAY)


def drag(start, end):
    move_to(*start)
    _post(Quartz.kCGEventLeftMouseDown, *start)
    time.sleep(STEP_DELAY)
    for step in range(1, DRAG_STEPS + 1):
        check_stop()
        x = start[0] + (end[0] - start[0]) * step / DRAG_STEPS
        y = start[1] + (end[1] - start[1]) * step / DRAG_STEPS
        _post(Quartz.kCGEventLeftMouseDragged, x, y)
        time.sleep(STEP_DELAY / 2)
    time.sleep(STEP_DELAY)
    _post(Quartz.kCGEventLeftMouseUp, *end)
    time.sleep(STEP_DELAY)


def app_at(x, y):
    """The app whose ordinary window is frontmost at a point, or None."""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    for window in windows:  # front to back
        if window.get("kCGWindowLayer") != NORMAL_WINDOW_LAYER:
            continue
        bounds = window["kCGWindowBounds"]
        inside_x = bounds["X"] <= x < bounds["X"] + bounds["Width"]
        inside_y = bounds["Y"] <= y < bounds["Y"] + bounds["Height"]
        if inside_x and inside_y:
            return AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
                window["kCGWindowOwnerPID"]
            )
    return None


def activate_window_at(x, y):
    """Bring forward the app showing at a point, so our first click counts as a
    move instead of only focusing the window."""
    app = app_at(x, y)
    if app is not None:
        app.activateWithOptions_(0)
        time.sleep(0.15)
