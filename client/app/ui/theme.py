"""
ExamSentinel UI Theme
=====================
Central palette, font, and spacing definitions used by every screen.
Plain Tkinter only — no third-party GUI libraries.

Palette: deep-navy dark theme with vivid blue accent.
"""

# ---------------------------------------------------------------------------
# Colour palette  (hex strings, ready for Tkinter `bg=` / `fg=`)
# ---------------------------------------------------------------------------

BG_PRIMARY = "#0A0E1A"          # Deep navy — root window / page background
BG_SECONDARY = "#141929"        # Slightly lighter — cards, panels
BG_INPUT = "#1A2036"            # Input fields, text areas

ACCENT = "#4E7AFF"              # Vivid blue — primary action buttons, links
ACCENT_HOVER = "#6B91FF"        # Lighter blue — hover state for accent

TEXT_PRIMARY = "#E8ECF4"        # Off-white — headings, body copy
TEXT_SECONDARY = "#8B92A8"      # Muted lavender-grey — labels, hints
TEXT_PLACEHOLDER = "#5C6280"    # Dimmed — placeholder text inside inputs

BORDER = "#2A3150"              # Subtle border for cards and inputs

SUCCESS = "#2DD4A8"             # Green-teal — success toasts, check marks
ERROR = "#FF4D6A"               # Coral-red — error toasts, validation
WARNING = "#FFB020"             # Amber — warning messages

# ---------------------------------------------------------------------------
# Font tuples  (family, size, ?weight)
# ---------------------------------------------------------------------------

FONT_HEADING = ("Segoe UI", 20, "bold")
FONT_SUBHEADING = ("Segoe UI", 14, "bold")
FONT_BODY = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_BUTTON = ("Segoe UI", 12, "bold")

# ---------------------------------------------------------------------------
# Spacing constants  (pixels)
# ---------------------------------------------------------------------------

PAD_LARGE = 24
PAD_MEDIUM = 16
PAD_SMALL = 8

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

BORDER_WIDTH = 1
CORNER_RADIUS = 6               # informational only (Tkinter has no CSS radius)
TOAST_DURATION_MS = 3000        # default toast display time
