"""Generate ExamSentinel icon.ico — lock symbol on accent blue background.

Produces multi-resolution ICO: 256, 128, 64, 48, 32, 16 px.
Run once:  python client/build/gen_icon.py
"""

from PIL import Image, ImageDraw, ImageFont
import os

ACCENT = (78, 122, 255)  # #4E7AFF
WHITE = (232, 236, 244)  # #E8ECF4
BG = (10, 14, 26)        # #0A0E1A
SIZES = [256, 128, 64, 48, 32, 16]
OUT = os.path.join(os.path.dirname(__file__), "icon.ico")


def draw_lock(size: int) -> Image.Image:
    """Draw a stylised padlock on accent background."""
    img = Image.new("RGBA", (size, size), ACCENT)
    d = ImageDraw.Draw(img)

    # Dimensions relative to icon size
    cx = size / 2
    cy = size / 2
    s = size  # shorthand

    # Shackle (arc at top)
    shackle_w = s * 0.38
    shackle_h = s * 0.30
    shackle_thick = max(s * 0.07, 2)
    shackle_bbox = [
        cx - shackle_w / 2, cy - s * 0.32,
        cx + shackle_w / 2, cy - s * 0.32 + shackle_h,
    ]
    d.arc(shackle_bbox, 180, 0, fill=WHITE, width=int(shackle_thick))
    # Shackle legs
    leg_top = cy - s * 0.32 + shackle_h / 2
    leg_bot = cy - s * 0.04
    d.line([(cx - shackle_w / 2, leg_top), (cx - shackle_w / 2, leg_bot)],
           fill=WHITE, width=int(shackle_thick))
    d.line([(cx + shackle_w / 2, leg_top), (cx + shackle_w / 2, leg_bot)],
           fill=WHITE, width=int(shackle_thick))

    # Body (rounded rectangle)
    body_w = s * 0.52
    body_h = s * 0.38
    body_top = cy - s * 0.04
    body_bbox = [
        cx - body_w / 2, body_top,
        cx + body_w / 2, body_top + body_h,
    ]
    r = s * 0.05
    d.rounded_rectangle(body_bbox, radius=r, fill=WHITE)

    # Keyhole (small dark circle + slit)
    kh_r = s * 0.055
    d.ellipse([cx - kh_r, body_top + body_h * 0.3 - kh_r,
               cx + kh_r, body_top + body_h * 0.3 + kh_r], fill=ACCENT)
    slit_w = max(s * 0.03, 1)
    d.rectangle([cx - slit_w, body_top + body_h * 0.3,
                 cx + slit_w, body_top + body_h * 0.65], fill=ACCENT)

    return img


def main():
    images = [draw_lock(s) for s in SIZES]
    images[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
                   append_images=images[1:])
    fsize = os.path.getsize(OUT)
    print(f"Created {OUT}  ({fsize:,} bytes, {len(SIZES)} resolutions)")


if __name__ == "__main__":
    main()
