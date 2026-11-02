"""Screen grabs.

Everything outside this module works in macOS screen points, the same units
mouse events use. A Retina display has 2 pixels per point, so each grab reports
its own scale.
"""

import mss
import numpy as np
import Quartz


class Screen:
    def __init__(self, shot, monitor):
        self._mss = shot
        self.monitor = monitor

    def grab(self, region=None):
        """Return (BGR image, pixels per point) for a region of points."""
        region = region or self.monitor
        shot = self._mss.grab(
            {
                "left": int(region["left"]),
                "top": int(region["top"]),
                "width": int(region["width"]),
                "height": int(region["height"]),
            }
        )
        image = np.asarray(shot)[:, :, :3].copy()
        return image, image.shape[1] / int(region["width"])


def all_screens():
    """One Screen per display. Create these on the thread that will use them."""
    shot = mss.mss()
    return [Screen(shot, monitor) for monitor in shot.monitors[1:]]


def has_screen_recording():
    return bool(Quartz.CGPreflightScreenCaptureAccess())


def request_screen_recording():
    """Ask macOS to list this app under Screen Recording in System Settings."""
    Quartz.CGRequestScreenCaptureAccess()
