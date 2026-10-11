"""WaveBoard Canvas Studio: frame, stretch, move and draw on canvases with your hands.

OpenCV draws straight to the projector and MediaPipe tracks two hands on the
CPU. Make an L with both hands to frame a new canvas, then pull your hands
apart to stretch it, like the TouchDesigner hand-tracking demos.

    python canvas_studio.py                    # camera + built-in sample slides
    python canvas_studio.py --slides ~/deck    # your slides exported as PNG/JPG
    python canvas_studio.py --no-camera        # mouse and keyboard only

Press H in the window for the gesture guide; Q or Esc quits.
"""

import argparse
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
import re
import threading
import time

import cv2
import numpy as np

from canvas_gestures import CONTENT_NAMES, CONTENTS, INK_COLORS, CanvasStudio, Hand, Rect, ScreenMap, snap_aspect
from gestures import HandIdentities, finger_states, image_geometry, pinch_ratios
import tracker

WINDOW = "WaveBoard Canvas Studio"
ROOT = Path(__file__).resolve().parent

# BGR colours, matching the web viewer's palette.
BACKGROUND = (29, 24, 16)
GRID = (52, 45, 36)
ACCENT = (134, 233, 184)
COPPER = (104, 153, 219)
MUTED = (181, 174, 154)
TEXT = (236, 238, 233)
DANGER = (80, 90, 235)
LASER, LASER_GLOW = (40, 40, 255), (120, 120, 255)
FRAME_IDLE = (150, 160, 150)
BOARD = (44, 58, 47)
LETTERBOX = (22, 20, 18)
SLIDE_PAPER = (238, 241, 244)
SLIDE_INK = (51, 41, 33)
SLIDE_MUTED = (120, 112, 104)
SLIDE_ACCENT = (70, 140, 60)
INK_BGR = {"yellow": (40, 215, 255), "red": (60, 60, 230), "cyan": (240, 210, 40),
           "green": (100, 225, 120), "white": (250, 250, 250), "black": (30, 30, 30)}
HAND_COLORS = (ACCENT, COPPER)
LINKS = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
         (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20))
FONT, FONT_BOLD = cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX

# waitKeyEx codes differ between GTK (JetPack's OpenCV), Qt (pip wheels) and Windows.
KEYS_NEXT = {32, 65363, 65364, 65366, 16777236, 16777237, 16777239, 2555904, 2621440, 2228224}
KEYS_PREVIOUS = {65361, 65362, 65365, 16777234, 16777235, 16777238, 2424832, 2490368, 2162688}
KEYS_DELETE = {65535, 16777223, 3014656}
KEYS_QUIT = {27, 16777216}

HELP_ROWS = (
    (("L + L", "frame & stretch a canvas"), ("PINCH", "move  (both hands: stretch)"),
     ("POINT", "laser / draw on whiteboard"), ("PALM SWIPE", "next / previous slide")),
    (("MIDDLE PINCH", "change content"), ("RING PINCH", "undo"),
     ("PINKY PINCH", "laser or pen colour"), ("DROP ON BIN", "delete canvas")),
)
HELP_KEYS = ("Keys: arrows/clicker slides  N new  C content  Z undo  X clear  K laser/pen  "
             "B background  V hands  T timings  S save  P pause  F fullscreen  H help  Q quit")


def now_ms():
    return int(time.monotonic() * 1000)


def text(image, value, origin, scale, color, thickness=1, font=FONT):
    cv2.putText(image, value, (int(origin[0]), int(origin[1])), font, scale, color, thickness, cv2.LINE_AA)


def text_width(value, scale, thickness=1, font=FONT):
    return cv2.getTextSize(value, font, scale, thickness)[0][0]


def shade(image, x0, y0, x1, y1, color, alpha):
    """Blend a translucent rectangle into the image in place."""
    x0, y0 = max(int(x0), 0), max(int(y0), 0)
    x1, y1 = min(int(x1), image.shape[1]), min(int(y1), image.shape[0])
    if x1 > x0 and y1 > y0:
        region = image[y0:y1, x0:x1]
        cv2.addWeighted(region, 1 - alpha, np.full_like(region, color), alpha, 0, dst=region)


def chip(image, value, origin, scale, color, background=(18, 16, 14), alpha=0.75):
    """Text on a small translucent label; origin is the text baseline."""
    (w, h), base = cv2.getTextSize(value, FONT, scale, 1)
    x, y = int(origin[0]), int(origin[1])
    shade(image, x - 6, y - h - 6, x + w + 6, y + base + 4, background, alpha)
    text(image, value, (x, y), scale, color)


def wrap(value, max_width, scale, thickness=1, font=FONT):
    lines, line = [], ""
    for word in value.split():
        candidate = f"{line} {word}".strip()
        if line and text_width(candidate, scale, thickness, font) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line] if line else lines


def dashed_rect(image, rect, color, thickness=2, dash=14, gap=9):
    x0, y0, x1, y1 = int(rect.x), int(rect.y), int(rect.x + rect.w), int(rect.y + rect.h)
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        length = max(abs(bx - ax), abs(by - ay))
        for start in range(0, length, dash + gap):
            end = min(start + dash, length)
            p = (ax + (bx - ax) * start // max(length, 1), ay + (by - ay) * start // max(length, 1))
            q = (ax + (bx - ax) * end // max(length, 1), ay + (by - ay) * end // max(length, 1))
            cv2.line(image, p, q, color, thickness, cv2.LINE_AA)


def corner_brackets(image, x0, y0, x1, y1, color, length, thickness=3):
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(image, (cx, cy), (cx + dx * length, cy), color, thickness, cv2.LINE_AA)
        cv2.line(image, (cx, cy), (cx, cy + dy * length), color, thickness, cv2.LINE_AA)


# ---- slides ----

def natural_key(path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def fit_within(image, size, limit=1.5):
    """Shrink very large slides once at load time to save memory and resize work."""
    scale = min(size[0] * limit / image.shape[1], size[1] * limit / image.shape[0], 1.0)
    if scale < 1.0:
        image = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)),
                           interpolation=cv2.INTER_AREA)
    return image


def sample_slides(size):
    """Built-in slides that double as a gesture tutorial."""
    w, h = size
    s = min(w / 1280, h / 720)
    left, right = int(90 * s), w - int(90 * s)

    def slide(kicker, title):
        image = np.full((h, w, 3), SLIDE_PAPER, np.uint8)
        cv2.rectangle(image, (0, 0), (int(14 * s), h), SLIDE_ACCENT, -1)
        text(image, kicker, (left, 120 * s), 0.6 * s, SLIDE_MUTED, 1)
        text(image, title, (left, 190 * s), 1.6 * s, SLIDE_INK, max(1, round(2 * s)), FONT_BOLD)
        return image

    def bullets(image, items, width, top=280):
        y = top * s
        for item in items:
            for line in wrap(item, width, 0.85 * s, max(1, round(2 * s))):
                text(image, line, (left, y), 0.85 * s, SLIDE_INK, max(1, round(2 * s)))
                y += 44 * s
            y += 16 * s

    title = np.full((h, w, 3), SLIDE_PAPER, np.uint8)
    cv2.rectangle(title, (0, 0), (int(14 * s), h), SLIDE_ACCENT, -1)
    text(title, "HANDS-ON PRESENTATIONS", (left, 250 * s), 0.7 * s, SLIDE_MUTED, max(1, round(2 * s)))
    text(title, "WaveBoard", (left - 6 * s, 365 * s), 3.6 * s, SLIDE_INK, max(2, round(7 * s)), FONT_BOLD)
    text(title, "Present, draw and build with your hands.", (left, 440 * s), 1.0 * s, SLIDE_INK, max(1, round(2 * s)))
    text(title, "Swipe an open palm to the left for the next slide", (left, 640 * s), 0.7 * s,
         SLIDE_ACCENT, max(1, round(2 * s)))

    frame = slide("GESTURE 01", "Frame a canvas")
    bullets(frame, ["1  Make an L with both hands: thumb and index finger out.",
                    "2  Hold the frame until the ring fills.",
                    "3  Pull your hands apart to stretch the canvas.",
                    "4  Relax both hands to place it. Squeeze them together first to cancel."], int(640 * s))
    box = Rect(840 * s, 260 * s, 330 * s, 240 * s)
    dashed_rect(frame, box, SLIDE_MUTED, max(1, round(2 * s)))
    length, thick = int(90 * s), max(2, round(10 * s))
    x0, y0, x1, y1 = int(box.x), int(box.y), int(box.x + box.w), int(box.y + box.h)
    for cx, cy, dx, dy in ((x0, y1, 1, -1), (x1, y0, -1, 1)):
        cv2.line(frame, (cx, cy), (cx + dx * length, cy), SLIDE_ACCENT, thick, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * length), SLIDE_ACCENT, thick, cv2.LINE_AA)

    move = slide("GESTURE 02", "Move, stretch, delete")
    bullets(move, ["Pinch thumb and index on a canvas to move it.",
                   "Pinch it with both hands and pull to stretch it.",
                   "Drop it on the bin at the bottom of the screen to delete it.",
                   "Thumb + middle pinch changes what a canvas shows: slides, whiteboard or a live camera lens."],
            right - left)

    draw = slide("GESTURE 03", "Draw and annotate")
    bullets(draw, ["Point with your index finger, thumb tucked in: on a whiteboard you draw,",
                   "on slides you get a laser pointer.",
                   "Thumb + pinky pinch picks the tool: laser pointer, then each pen colour.",
                   "Pen ink stays with its slide or canvas and stretches with it.",
                   "Thumb + ring pinch: undo.  Keyboard: Z undo, X clear, K laser / pen."], right - left)

    own = slide("SETUP", "Bring your own slides")
    bullets(own, ["Export your deck as images, one file per slide (PowerPoint: File > Export > PNG).",
                  "Or export a PDF and run:  pdftoppm -png -r 110 deck.pdf ~/my-deck/slide",
                  "Then start:  python canvas_studio.py --slides ~/my-deck",
                  "Arrow keys, Page Up/Down and presenter clickers change slides too."], right - left)
    return [title, frame, move, draw, own]


class SlideDeck:
    EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    def __init__(self, folder, screen_size):
        self.images, self.sample = [], folder is None
        if folder is None:
            self.images = sample_slides(screen_size)
        else:
            folder = Path(folder).expanduser()
            if not folder.is_dir():
                raise SystemExit(f"Slides folder not found: {folder}")
            for path in sorted((p for p in folder.iterdir() if p.suffix.lower() in self.EXTENSIONS), key=natural_key):
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    print(f"Skipping unreadable slide: {path.name}")
                    continue
                self.images.append(fit_within(image, screen_size))
            if not self.images:
                raise SystemExit(f"No PNG or JPG slides found in {folder}")
        self._cache = OrderedDict()

    def __len__(self):
        return len(self.images)

    def fitted(self, page, size):
        """The slide letterboxed into a canvas of this size (cached while the size holds)."""
        key = (page, size)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        w, h = size
        image = self.images[page]
        scale = min(w / image.shape[1], h / image.shape[0])
        sw, sh = max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))
        result = np.full((h, w, 3), LETTERBOX, np.uint8)
        x, y = (w - sw) // 2, (h - sh) // 2
        result[y:y + sh, x:x + sw] = cv2.resize(image, (sw, sh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        self._cache[key] = result
        while len(self._cache) > 6:
            self._cache.popitem(last=False)
        return result


# ---- live camera lenses ----

def lens_neon(image):
    # Edges at half resolution: cleaner outlines, less wall texture and sensor noise, less work.
    h, w = image.shape[:2]
    gray = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (max(1, w // 2), max(1, h // 2)),
                      interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (7, 7), 0), 70, 160)
    edges = cv2.resize(edges, (w, h), interpolation=cv2.INTER_LINEAR)
    glow = cv2.convertScaleAbs(cv2.GaussianBlur(edges, (0, 0), 5), alpha=2.5)
    neon = cv2.merge([cv2.max(edges, glow), cv2.max(edges, cv2.convertScaleAbs(glow, alpha=0.85)),
                      cv2.convertScaleAbs(edges, alpha=0.9)])
    return cv2.add(cv2.convertScaleAbs(image, alpha=0.15), neon)


def lens_thermal(image):
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    return cv2.applyColorMap(gray, getattr(cv2, "COLORMAP_INFERNO", cv2.COLORMAP_JET))


def lens_pixel(image):
    h, w = image.shape[:2]
    block = max(8, min(w, h) // 24)
    small = cv2.resize(image, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def lens_xray(image):
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    return cv2.applyColorMap(cv2.bitwise_not(gray), cv2.COLORMAP_BONE)


LENSES = {"neon": lens_neon, "thermal": lens_thermal, "pixel": lens_pixel, "xray": lens_xray}


def lens_view(effect, camera, visible, full):
    """The lens effect for the visible part of a canvas, aligned with the camera background."""
    vx0, vy0, vx1, vy1 = visible
    if effect == "magnify":
        # Show the middle of the canvas region at twice the size.
        x0, y0, x1, y1 = full
        sx0, sy0 = (3 * x0 + x1) / 4, (3 * y0 + y1) / 4
        matrix = np.float32([[2, 0, x0 - vx0 - 2 * sx0], [0, 2, y0 - vy0 - 2 * sy0]])
        return cv2.warpAffine(camera, matrix, (vx1 - vx0, vy1 - vy0), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
    return LENSES[effect](camera[vy0:vy1, vx0:vx1])


# ---- drawing the screen ----

class Renderer:
    def __init__(self, size, deck):
        self.size = size
        self.deck = deck
        self.background_mode = 0  # dimmed camera, full camera, plain
        self.show_help = True
        self.show_hands = True
        self.show_timings = False
        w, h = size
        self.base = np.full((h, w, 3), BACKGROUND, np.uint8)
        step = max(40, w // 32)
        for x in range(step // 2, w, step):
            cv2.line(self.base, (x, 0), (x, h), GRID, 1)
        for y in range(step // 2, h, step):
            cv2.line(self.base, (0, y), (w, y), GRID, 1)

    def compose(self, studio, overlay, camera, hands, t, stats, mouse=None, status=None):
        if camera is not None and self.background_mode == 0:
            out = cv2.addWeighted(camera, 0.38, self.base, 0.62, 0)
        elif camera is not None and self.background_mode == 1:
            out = camera.copy()
        else:
            out = self.base.copy()
        for canvas in studio.canvases:
            self.draw_canvas(out, canvas, camera, canvas.id == studio.focus)
        if overlay["ghost"]:
            self.draw_ghost(out, overlay["ghost"]["rect"], overlay["ghost"]["progress"])
        if mouse and mouse.ghost:
            dashed_rect(out, mouse.ghost, ACCENT)
        mouse_moving = bool(mouse and mouse.action and mouse.action[0] == "move")
        dragging = overlay["trash"]["visible"] or mouse_moving
        if dragging:
            hot = overlay["trash"]["hot"] or (mouse_moving and studio.in_trash(mouse.position))
            self.draw_trash(out, studio, hot)
        if self.show_hands:
            for index, hand in enumerate(hands):
                self.draw_hand(out, hand, HAND_COLORS[index % 2])
        for cursor in overlay["cursors"]:
            self.draw_cursor(out, cursor, studio)
        # The help strip would cover the bin, so it steps aside while a canvas is held.
        self.draw_hud(out, studio, overlay, t, stats, status, self.show_help and not dragging)
        return out

    def draw_canvas(self, out, canvas, camera, focused):
        w_screen, h_screen = self.size
        r = canvas.rect
        x0, y0, x1, y1 = round(r.x), round(r.y), round(r.x + r.w), round(r.y + r.h)
        w, h = x1 - x0, y1 - y0
        if w < 4 or h < 4:
            return
        vx0, vy0, vx1, vy1 = max(x0, 0), max(y0, 0), min(x1, w_screen), min(y1, h_screen)
        if vx1 <= vx0 or vy1 <= vy0:
            return
        view = out[vy0:vy1, vx0:vx1]
        if canvas.content == "slides" and len(self.deck):
            full = self.deck.fitted(min(canvas.page, len(self.deck) - 1), (w, h))
            view[:] = full[vy0 - y0:vy1 - y0, vx0 - x0:vx1 - x0]
        elif canvas.content.startswith("lens:"):
            if camera is None:
                view[:] = LETTERBOX
                if w > 120 and h > 40:
                    text(out, "camera off", (x0 + w / 2 - 55, y0 + h / 2 + 6), 0.6, MUTED)
            else:
                view[:] = lens_view(canvas.content[5:], camera, (vx0, vy0, vx1, vy1), (x0, y0, x1, y1))
        else:
            view[:] = BOARD
        self.draw_ink(out, canvas, x0, y0, w, h)

        color = COPPER if canvas.forming else ACCENT if focused else FRAME_IDLE
        cv2.rectangle(out, (x0, y0), (x1 - 1, y1 - 1), color, 1, cv2.LINE_AA)
        corner_brackets(out, x0, y0, x1 - 1, y1 - 1, color, int(min(28, w / 4, h / 4)))
        if canvas.content == "slides":
            label = f"SLIDE {min(canvas.page, len(self.deck) - 1) + 1}/{len(self.deck)}"
        else:
            label = CONTENT_NAMES[canvas.content].upper()
        if canvas.forming:
            label += f"  {w} x {h}"
        chip(out, label, (x0 + 4, y0 - 10 if y0 > 30 else y0 + 22), 0.45, color)

    @staticmethod
    def draw_ink(out, canvas, x0, y0, w, h):
        thickness = max(2, round(min(w, h) * 0.008))
        for stroke in canvas.ink.get(canvas.layer(), ()):
            color = INK_BGR.get(stroke.color, TEXT)
            points = np.rint(np.asarray(stroke.points, np.float32) * (w, h) + (x0, y0)).astype(np.int32)
            if len(points) == 1:
                cv2.circle(out, (int(points[0][0]), int(points[0][1])), thickness, color, -1, cv2.LINE_AA)
            else:
                cv2.polylines(out, [points.reshape(-1, 1, 2)], False, color, thickness, cv2.LINE_AA)

    @staticmethod
    def draw_ghost(out, rect, progress):
        dashed_rect(out, rect, ACCENT)
        cx, cy = (int(v) for v in rect.center)
        cv2.circle(out, (cx, cy), 26, (70, 80, 80), 3, cv2.LINE_AA)
        cv2.ellipse(out, (cx, cy), (26, 26), -90, 0, 360 * progress, ACCENT, 3, cv2.LINE_AA)
        chip(out, "HOLD", (cx - 20, cy + 52), 0.5, ACCENT)

    @staticmethod
    def draw_trash(out, studio, hot):
        (cx, cy), radius = studio.trash
        cx, cy, radius = int(cx), int(cy), int(radius)
        cv2.circle(out, (cx, cy), radius, (40, 40, 120) if hot else (35, 32, 30), -1, cv2.LINE_AA)
        color = DANGER if hot else MUTED
        cv2.circle(out, (cx, cy), radius, color, 2, cv2.LINE_AA)
        cv2.rectangle(out, (cx - 12, cy - 8), (cx + 12, cy + 18), color, 2, cv2.LINE_AA)
        cv2.line(out, (cx - 17, cy - 13), (cx + 17, cy - 13), color, 2, cv2.LINE_AA)
        cv2.line(out, (cx - 5, cy - 18), (cx + 5, cy - 18), color, 2, cv2.LINE_AA)
        for x in (cx - 5, cx + 5):
            cv2.line(out, (x, cy - 3), (x, cy + 13), color, 1, cv2.LINE_AA)
        label = "RELEASE TO DELETE" if hot else "DROP TO DELETE"
        chip(out, label, (cx - text_width(label, 0.45) / 2, cy - radius - 12), 0.45, color)

    @staticmethod
    def draw_hand(out, hand, color):
        points = [(int(x), int(y)) for x, y in hand.points]
        for a, b in LINKS:
            cv2.line(out, points[a], points[b], color, 2, cv2.LINE_AA)
        for index, point in enumerate(points):
            cv2.circle(out, point, 5 if index in (4, 8, 12, 16, 20) else 3, color, -1, cv2.LINE_AA)

    @staticmethod
    def draw_cursor(out, cursor, studio):
        x, y = (int(v) for v in cursor["pos"])
        pose = cursor["pose"]
        if pose == "point" and cursor["laser"] and not cursor["drawing"]:
            trail = cursor["laser"]
            for i, (a, b) in enumerate(zip(trail, trail[1:])):
                width = 1 + round(5 * (i + 1) / len(trail))
                cv2.line(out, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), LASER, width, cv2.LINE_AA)
            cv2.circle(out, (x, y), 14, LASER_GLOW, 2, cv2.LINE_AA)
            cv2.circle(out, (x, y), 8, LASER, -1, cv2.LINE_AA)
            cv2.circle(out, (x, y), 3, (230, 230, 255), -1, cv2.LINE_AA)
        elif pose == "point":
            cv2.circle(out, (x, y), 10, TEXT, 2, cv2.LINE_AA)
            cv2.circle(out, (x, y), 6, INK_BGR[INK_COLORS[studio.ink]], -1, cv2.LINE_AA)
        elif pose.startswith("pinch:"):
            if cursor["grabbing"]:
                cv2.circle(out, (x, y), 13, ACCENT, -1, cv2.LINE_AA)
            cv2.circle(out, (x, y), 13, TEXT, 2, cv2.LINE_AA)
            if pose != "pinch:index":
                chip(out, pose[6:].upper(), (x + 18, y + 5), 0.45, ACCENT)
        elif pose == "frame":
            cv2.line(out, (x - 12, y - 12), (x - 12, y + 12), ACCENT, 3, cv2.LINE_AA)
            cv2.line(out, (x - 12, y + 12), (x + 12, y + 12), ACCENT, 3, cv2.LINE_AA)
        elif pose == "open":
            cv2.circle(out, (x, y), 24, MUTED, 1, cv2.LINE_AA)
        else:
            cv2.circle(out, (x, y), 9, MUTED, 1, cv2.LINE_AA)

    def draw_hud(self, out, studio, overlay, t, stats, status, show_help):
        w, h = self.size
        shade(out, 0, 0, w, 64, (18, 16, 14), 0.55)
        text(out, "WAVEBOARD", (22, 30), 0.75, TEXT, 2, FONT_BOLD)
        text(out, "CANVAS STUDIO", (22 + text_width("WAVEBOARD", 0.75, 2, FONT_BOLD) + 12, 30), 0.45, MUTED)
        text(out, overlay["mode"].upper(), (22, 54), 0.5, ACCENT)
        readout = f"CAM {stats['capture']:4.1f}  TRACK {stats['tracking']:4.1f}  DRAW {stats['render']:4.1f} FPS"
        text(out, readout, (w - text_width(readout, 0.45) - 22, 30), 0.45, MUTED)
        ink = INK_COLORS[studio.ink]
        text(out, "LASER POINTER" if studio.laser else f"PEN {ink.upper()}", (w - 160, 54), 0.45, MUTED)
        cv2.circle(out, (w - 175, 49), 7, LASER if studio.laser else INK_BGR[ink], -1, cv2.LINE_AA)
        message = studio.message(t)
        if message:
            chip(out, message, (w / 2 - text_width(message, 0.65) / 2, 106), 0.65, TEXT, alpha=0.8)
        bottom = h
        if show_help:
            bottom = h - 104
            shade(out, 0, bottom, w, h, (18, 16, 14), 0.7)
            column = (w - 44) / 4
            for row, items in enumerate(HELP_ROWS):
                for col, (gesture, action) in enumerate(items):
                    x, y = 22 + col * column, bottom + 28 + row * 28
                    text(out, gesture, (x, y), 0.45, ACCENT)
                    text(out, action, (x + text_width(gesture, 0.45) + 10, y), 0.45, TEXT)
            text(out, HELP_KEYS, (22, h - 16), 0.4, MUTED)
        if status:
            chip(out, status, (22, bottom - 16), 0.5, (140, 170, 255))
        if self.show_timings:
            lines = [f"{name:<9}{ms:6.1f} ms" for name, ms in stats.get("timings", {}).items()]
            lines.append(f"{'tracking':<9}{stats.get('tracking_ms', 0.0):6.1f} ms (own thread)")
            for i, line in enumerate(lines):
                chip(out, line, (w - 260, 96 + i * 26), 0.5, TEXT)


# ---- input: camera + MediaPipe, mouse ----

class HandTracker:
    """Camera capture and MediaPipe hand tracking, each in its own thread.

    Drawing never waits for tracking. On a Jetson's CPU, MediaPipe is slower
    than the camera, so drawing once per tracking result would cap the whole
    picture at the tracking rate. Instead the render loop draws every camera
    frame (frame()) and applies each finished tracking result once (result()).
    """

    def __init__(self, args):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        self.mp = mp
        self.processing_width = args.processing_width
        options = tracker.landmarker_options(python, vision, args)
        camera, self.info = tracker.open_camera(cv2, args)
        self.stop = threading.Event()
        self.capture = tracker.LatestFrameCapture(camera, self.stop)
        self.capture.start()
        try:
            self.landmarker = vision.HandLandmarker.create_from_options(options)
        except Exception:
            self.stop.set()
            self.capture.close()
            raise
        self.error = None
        self.tracking_fps = 0.0
        self.tracking_ms = 0.0
        self._lock = threading.Lock()
        self._result, self._result_id, self._taken_id = None, 0, 0
        self._thread = threading.Thread(target=self._track, name="hand-tracking", daemon=True)
        self._thread.start()

    def frame(self, after, timeout):
        """The newest camera sample (sequence, capture time, frame, capture fps).

        Waits up to timeout for one newer than `after`, then returns whatever is newest.
        """
        return self.capture.next_after(after, timeout=timeout) or self.capture.newest()

    def result(self):
        """Each finished tracking result once: (frame size, detections, timestamp ms), else None."""
        with self._lock:
            if self._result_id == self._taken_id:
                return None
            self._taken_id = self._result_id
            return self._result

    def _track(self):
        sequence, last_timestamp, last_frame = 0, -1, time.monotonic()
        meter = tracker.RateMeter()
        try:
            while not self.stop.is_set():
                sample = self.capture.next_after(sequence, timeout=0.25)
                if sample is None:
                    if time.monotonic() - last_frame > 5:
                        raise RuntimeError("No camera frames for five seconds. Check USB and the selected capture mode.")
                    continue
                sequence, capture_time, frame, _ = sample
                last_frame = time.monotonic()
                timestamp = int(capture_time * 1000)
                if timestamp <= last_timestamp:
                    continue
                last_timestamp = timestamp
                started = time.perf_counter()
                # Shrink first, then mirror the small image: same landmarks, far less work.
                height, width = frame.shape[:2]
                inference_width = min(width, self.processing_width)
                small = frame if inference_width == width else cv2.resize(
                    frame, (inference_width, max(1, round(height * inference_width / width))), interpolation=cv2.INTER_AREA)
                detections, _ = tracker.detect_hands(cv2, self.mp, np, self.landmarker, cv2.flip(small, 1),
                                                     timestamp, inference_width)
                self.tracking_ms = (time.perf_counter() - started) * 1000
                with self._lock:
                    self._result = ((width, height), detections, timestamp)
                    self._result_id += 1
                self.tracking_fps = meter.tick(time.monotonic())
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def close(self):
        self.stop.set()
        self._thread.join(timeout=2.0)
        self.capture.close()
        if not self._thread.is_alive():
            # Never close the landmarker while a detection may still be running.
            self.landmarker.close()


FRAME_PERIOD = 1 / 30


class StageTimer:
    """Average milliseconds per stage of a frame, for the T panel and the summary at exit."""

    def __init__(self):
        self.mean, self.total, self.count = {}, {}, {}

    def add(self, name, started):
        ms = (time.perf_counter() - started) * 1000
        self.mean[name] = ms if name not in self.mean else 0.9 * self.mean[name] + 0.1 * ms
        self.total[name] = self.total.get(name, 0.0) + ms
        self.count[name] = self.count.get(name, 0) + 1

    def summary(self):
        if not self.count:
            return "No frames were drawn."
        parts = [f"{name} {self.total[name] / self.count[name]:.1f}" for name in self.total]
        return "Average ms per frame: " + ", ".join(parts)


def matching_map(screen_map, frame_size, size, margin):
    if screen_map is None or screen_map.camera_size != frame_size:
        screen_map = ScreenMap(frame_size, size, margin)
    return screen_map


def camera_to_screen(frame, screen_map, size):
    """Crop, scale and mirror a camera frame for the background and lenses.

    Cropping the matching columns of the unmirrored frame and mirroring the
    scaled result equals cropping the mirrored frame, without flipping the
    full-size image every frame.
    """
    x, y, w, h = screen_map.crop
    mirrored_x = frame.shape[1] - x - w
    return cv2.flip(cv2.resize(frame[y:y + h, mirrored_x:mirrored_x + w], size, interpolation=cv2.INTER_LINEAR), 1)


class HandReader:
    """Detections -> screen-space Hand records with stable identities and debounced pinches."""

    def __init__(self):
        self.identities = HandIdentities()
        self.last_timestamp = None

    def read(self, detections, timestamp, frame_size, screen_map):
        if self.last_timestamp is not None and timestamp - self.last_timestamp > 500:
            self.identities.assign([])  # a stalled camera is a loss of tracking
        self.last_timestamp = timestamp
        aspect = frame_size[0] / frame_size[1]
        hands = []
        for detection, track in zip(detections, self.identities.assign(detections)):
            landmarks = detection["landmarks"]
            fingers = finger_states(detection.get("world_landmarks") or image_geometry(landmarks, aspect))
            pinches = track.pinch.update(pinch_ratios(landmarks, aspect), timestamp)
            points = [screen_map.to_screen(x, y) for x, y, _ in landmarks]
            hands.append(Hand(track.identity, points, fingers, pinches))
        return hands


class MouseControl:
    """Mouse fallback: drag empty space to make a canvas, drag a canvas to move it, drag its
    lower-right corner to resize it, right-drag to draw, scroll to scale."""

    HANDLE = 22

    def __init__(self, studio):
        self.studio = studio
        self.action = None
        self.ghost = None
        self.position = (0, 0)

    def __call__(self, event, x, y, flags, _param):
        studio, t, point = self.studio, now_ms(), (x, y)
        studio.tick(t)
        self.position = point
        if event == cv2.EVENT_LBUTTONDOWN:
            canvas = studio.canvas_at(point)
            if canvas is None:
                self.action, self.ghost = ("create", point), Rect(x, y, 0, 0)
            else:
                studio.raise_canvas(canvas)
                r = canvas.rect
                corner = abs(x - (r.x + r.w)) <= self.HANDLE and abs(y - (r.y + r.h)) <= self.HANDLE
                self.action = ("resize" if corner else "move", canvas.id, r.copy(), point)
        elif event == cv2.EVENT_RBUTTONDOWN:
            canvas = studio.canvas_at(point)
            if canvas:
                self.action = ("draw", canvas.id, studio.start_stroke(canvas, point, t))
        elif event == cv2.EVENT_MOUSEMOVE and self.action:
            self._drag(point, t)
        elif event in (cv2.EVENT_LBUTTONUP, cv2.EVENT_RBUTTONUP) and self.action:
            self._release(point)
        elif event == cv2.EVENT_MOUSEWHEEL:
            canvas = studio.canvas_at(point)
            if canvas:
                factor = 1.08 if cv2.getMouseWheelDelta(flags) > 0 else 1 / 1.08
                r = canvas.rect
                canvas.rect = Rect(x - (x - r.x) * factor, y - (y - r.y) * factor, r.w * factor, r.h * factor)

    def _drag(self, point, t):
        studio, kind = self.studio, self.action[0]
        if kind == "create":
            self.ghost = Rect.around([self.action[1], point])
            return
        canvas = studio.get(self.action[1])
        if canvas is None:
            self.action = None
        elif kind == "draw":
            if canvas.rect.contains(point):
                studio.extend_stroke(canvas, self.action[2], point, t)
        else:
            _, _, start, origin = self.action
            dx, dy = point[0] - origin[0], point[1] - origin[1]
            if kind == "move":
                canvas.rect = studio.keep_visible(Rect(start.x + dx, start.y + dy, start.w, start.h))
            else:
                canvas.rect = Rect(start.x, start.y, max(studio.min_size[0], start.w + dx),
                                   max(studio.min_size[1], start.h + dy))

    def _release(self, point):
        studio, kind = self.studio, self.action[0]
        if kind == "create":
            rect = Rect.around([self.action[1], point])
            if rect.w >= studio.min_size[0] and rect.h >= studio.min_size[1]:
                canvas = studio.add_canvas(snap_aspect(rect))
                studio.notify(f"{CONTENT_NAMES[canvas.content]} placed")
            self.ghost = None
        elif kind == "move" and studio.in_trash(point):
            canvas = studio.get(self.action[1])
            if canvas:
                studio.remove(canvas)
                studio.notify("Canvas deleted")
        self.action = None


# ---- main loop ----

def handle_key(key, studio, renderer, last_image):
    """Apply one key press. Returns False to quit."""
    if key in KEYS_NEXT or key in KEYS_PREVIOUS:
        target = studio.slide_target()
        if target:
            studio.turn_page(target, 1 if key in KEYS_NEXT else -1)
        else:
            studio.notify("No slides canvas: press C on a canvas to show slides")
        return True
    canvas = studio.focused()
    if key in KEYS_QUIT:
        return False
    if key in KEYS_DELETE:
        if canvas:
            studio.remove(canvas)
            studio.notify("Canvas deleted")
        return True
    if key >= 256:
        return True
    char = chr(key).lower()
    if char == "q":
        return False
    if char == "f":
        fullscreen = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL if fullscreen else cv2.WINDOW_FULLSCREEN)
    elif char == "h":
        renderer.show_help = not renderer.show_help
    elif char == "b":
        renderer.background_mode = (renderer.background_mode + 1) % 3
        studio.notify(("Dimmed camera", "Camera", "Plain")[renderer.background_mode] + " background")
    elif char == "v":
        renderer.show_hands = not renderer.show_hands
    elif char == "t":
        renderer.show_timings = not renderer.show_timings
    elif char == "p":
        studio.paused = not studio.paused
        studio.notify("Gestures paused" if studio.paused else "Gestures on")
    elif char == "n":
        w, h = studio.width * 0.42, studio.height * 0.42
        new = studio.add_canvas(snap_aspect(Rect((studio.width - w) / 2, (studio.height - h) / 2, w, h)))
        studio.notify(f"{CONTENT_NAMES[new.content]} placed")
    elif char == "k":
        studio.next_tool()
    elif char == "s" and last_image is not None:
        folder = ROOT / "captures"
        folder.mkdir(exist_ok=True)
        path = folder / f"waveboard-{datetime.now():%Y%m%d-%H%M%S}.png"
        cv2.imwrite(str(path), last_image)
        studio.notify(f"Saved captures/{path.name}")
    elif canvas and char == "c":
        studio.cycle_content(canvas)
    elif canvas and char == "z":
        studio.undo(canvas)
    elif canvas and char == "x":
        studio.clear(canvas)
    return True


def screen_size(value):
    match = re.fullmatch(r"(\d+)[xX](\d+)", value)
    if not match or int(match[1]) < 320 or int(match[2]) < 240:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, at least 320x240, e.g. 1280x720")
    return int(match[1]), int(match[2])


def reach(value):
    number = float(value)
    if not 0 <= number <= 0.3:
        raise argparse.ArgumentTypeError("must be between 0 and 0.3")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="WaveBoard Canvas Studio: frame, stretch, move and draw on "
                                                 "canvases with your hands.")
    tracker.register_camera_arguments(parser)
    parser.add_argument("--slides", type=Path, help="folder of slide images (PNG/JPG), shown in file-name order")
    parser.add_argument("--screen", type=screen_size, default=(1280, 720),
                        help="render size WIDTHxHEIGHT; the window scales it to the display (default 1280x720)")
    parser.add_argument("--reach", type=reach, default=0.12,
                        help="fraction of each camera edge to ignore so hands can reach the screen edges (default 0.12)")
    parser.add_argument("--new-canvas", choices=CONTENTS, default="lens:neon", help="what a newly framed canvas shows")
    parser.add_argument("--windowed", action="store_true", help="start in a window instead of fullscreen")
    parser.add_argument("--no-camera", action="store_true", help="mouse and keyboard only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    size = args.screen
    deck = SlideDeck(args.slides, size)
    studio = CanvasStudio(*size, slide_count=len(deck), new_content=args.new_canvas)
    # Opening slides canvas between the top bar and the help strip, in the deck's shape.
    w, h = size
    first = deck.images[0]
    ch = h * 0.72
    cw = min(w * 0.9, ch * first.shape[1] / first.shape[0])
    studio.add_canvas(Rect((w - cw) / 2, h * 0.115, cw, ch), "slides")
    renderer = Renderer(size, deck)
    reader = HandReader()
    status = None
    hand_tracker = None
    if args.no_camera:
        status = "Camera off: drag to make canvases, right-drag to draw, scroll to resize."
    else:
        try:
            hand_tracker = HandTracker(args)
        except Exception as exc:
            status = f"Hand tracking unavailable ({exc}). Mouse and keyboard still work."
            print(status)
    try:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    except cv2.error as exc:
        if hand_tracker:
            hand_tracker.close()
        raise SystemExit(f"Cannot open a window ({exc}). Run this from the Jetson desktop session.")
    cv2.resizeWindow(WINDOW, w, h)
    if not args.windowed:
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    mouse = MouseControl(studio)
    cv2.setMouseCallback(WINDOW, mouse)
    print("WaveBoard Canvas Studio running. Press H for help, Q or Esc to quit.", flush=True)

    camera_view, screen_map, hands, image = None, None, [], None
    frame_sequence, capture_fps = 0, 0.0
    overlay = studio.update([], now_ms())
    render_meter, timer = tracker.RateMeter(), StageTimer()
    presented = time.perf_counter()
    try:
        while True:
            if hand_tracker and hand_tracker.error:
                status = f"Hand tracking stopped ({hand_tracker.error}). Mouse and keyboard still work."
                hand_tracker.close()
                hand_tracker, camera_view, hands = None, None, []
            if hand_tracker:
                # Draw each new camera frame at once; without one, still draw ~30 times a second.
                try:
                    sample = hand_tracker.frame(frame_sequence, max(0.0, presented + FRAME_PERIOD - time.perf_counter()))
                except RuntimeError as exc:
                    hand_tracker.close()
                    hand_tracker, camera_view, hands, sample = None, None, [], None
                    status = f"{exc} Mouse and keyboard still work."
                started = time.perf_counter()
                if sample and sample[0] != frame_sequence:
                    frame_sequence, _, frame, capture_fps = sample
                    screen_map = matching_map(screen_map, (frame.shape[1], frame.shape[0]), size, args.reach)
                    camera_view = camera_to_screen(frame, screen_map, size)
                timer.add("camera", started)
                started = time.perf_counter()
                result = hand_tracker.result() if hand_tracker else None
                if result:
                    frame_size, detections, timestamp = result
                    screen_map = matching_map(screen_map, frame_size, size, args.reach)
                    hands = reader.read(detections, timestamp, frame_size, screen_map)
                    overlay = studio.update(hands, timestamp)
                timer.add("gestures", started)
            else:
                overlay = studio.update([], now_ms())
            started = time.perf_counter()
            stats = {"capture": capture_fps if hand_tracker else 0.0,
                     "tracking": hand_tracker.tracking_fps if hand_tracker else 0.0,
                     "tracking_ms": hand_tracker.tracking_ms if hand_tracker else 0.0,
                     "render": render_meter.tick(time.monotonic()), "timings": timer.mean}
            image = renderer.compose(studio, overlay, camera_view, hands, now_ms(), stats, mouse, status)
            timer.add("draw", started)
            started = time.perf_counter()
            cv2.imshow(WINDOW, image)
            key = cv2.waitKeyEx(1 if hand_tracker else 15)
            presented = time.perf_counter()
            timer.add("display", started)
            studio.tick(now_ms())
            if key != -1 and not handle_key(key, studio, renderer, image):
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if hand_tracker:
            hand_tracker.close()
        cv2.destroyAllWindows()
        print(timer.summary(), flush=True)


if __name__ == "__main__":
    main()
