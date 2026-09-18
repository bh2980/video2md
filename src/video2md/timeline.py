from __future__ import annotations

from bisect import bisect_right

from video2md.models import ScreenBlock, ScreenEvent, SpeechCue, SpeechEvent, TimelineEvent


def merge(cues: list[SpeechCue], screens: list[ScreenBlock]) -> list[TimelineEvent]:
    """Merge speech cues and screen blocks into a single time-ordered event list.

    Events are sorted by (sort_t, kind_rank): at identical timestamps,
    screen events (kind_rank=0) come before speech events (kind_rank=1).
    OCR text is never spliced into speech text.
    """
    events: list[TimelineEvent] = [
        *[SpeechEvent(start_s=c.start_s, end_s=c.end_s, text=c.text) for c in cues],
        *[ScreenEvent(t_s=s.t_s, block=s) for s in screens],
    ]
    events.sort(key=lambda e: (e.sort_t, e.kind_rank))
    return events


def group_cues_under_screens(
    cues: list[SpeechCue], screens: list[ScreenBlock]
) -> list[tuple[ScreenBlock | None, list[SpeechCue]]]:
    """Group speech cues under the screen frame they belong to.

    Each cue is attached to the frame whose capture time bounds it via a
    half-open interval: frame i owns cues with
    ``t_i <= cue.start_s < t_{i+1}``. The last frame owns
    ``[t_last, +inf)``. Cues starting before the first frame attach to the
    first frame (they render after that Screen block, never before it).

    Returns one ``(screen, cues_for_screen)`` tuple per screen, in frame
    order. Each cue keeps its own timestamps and text — nothing is merged.

    With no screens, returns a single ``(None, cues)`` group so the
    speech-only timeline is unchanged.
    """
    if not screens:
        return [(None, sorted(cues, key=lambda c: c.start_s))]

    ordered = sorted(screens, key=lambda s: s.t_s)
    groups: list[tuple[ScreenBlock | None, list[SpeechCue]]] = [(s, []) for s in ordered]
    starts = [s.t_s for s in ordered]

    for cue in sorted(cues, key=lambda c: c.start_s):
        idx = bisect_right(starts, cue.start_s) - 1
        if idx < 0:
            idx = 0
        groups[idx][1].append(cue)
    return groups
