"""Differences between the places a board can live."""

from dataclasses import dataclass

MAC_CHESS_BUNDLE_ID = "com.apple.Chess"


@dataclass(frozen=True)
class Profile:
    # Websites pop up a piece picker on promotion, with the queen sitting on
    # the promotion square, so one more click there chooses it.
    click_to_promote: bool


def profile_for(bundle_id):
    """Pick the profile for the app showing the board."""
    return Profile(click_to_promote=bundle_id != MAC_CHESS_BUNDLE_ID)
