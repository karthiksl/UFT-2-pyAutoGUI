"""Screen player — simulated Epic+Citrix window for the sample dry-run.

This tkinter window displays the generated mock screen PNGs in sequence,
acting as the "desktop" that the automation framework clicks against.

Usage
-----
    python fixtures/sample_uft/screen_player.py

Controls
--------
    F8           Advance to the next screen manually.
    Escape       Quit.
    Mouse click  Detected; triggers automatic screen advance when the click
                 lands inside a registered "hot zone" (e.g. Login button,
                 Coverage tab).

Screen sequence
---------------
    0 → login.png
    1 → home.png
    2 → coverage.png
    (wraps back to 0 after coverage)

Hot zones (auto-advance on click)
----------------------------------
    login.png    Login button area   (570,366)–(710,408) → home
    home.png     Coverage tab area   (162,135)–(322,173) → coverage

Notes
-----
* The window is placed at (0, 0) by default so that OR regions match the
  displayed pixel coordinates exactly (1280×800 at 100 % DPI).
* On macOS with Retina display the tkinter canvas may use logical pixels
  (half the physical resolution).  The script detects this and warns, but
  still runs — the automation test should set PYAUTOGUI_SCALE=2 in that case.
* Requires only stdlib tkinter + Pillow.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from typing import NamedTuple

try:
    from PIL import Image, ImageTk
except ImportError:
    print("ERROR: Pillow is required.  pip install Pillow", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_SCREENS = _HERE / "screens"

_SCREEN_FILES = [
    _SCREENS / "login.png",
    _SCREENS / "home.png",
    _SCREENS / "coverage.png",
]

_SCREEN_NAMES = ["login", "home", "coverage"]

# ---------------------------------------------------------------------------
# Hot zones — (x0, y0, x1, y1, next_screen_index)
# Coordinates are absolute pixels within the 1280×800 canvas.
# ---------------------------------------------------------------------------
class _HotZone(NamedTuple):
    x0: int
    y0: int
    x1: int
    y1: int
    target_screen: int
    label: str


_HOT_ZONES: dict[int, list[_HotZone]] = {
    # Screen 0 (login) — Login button advances to home
    0: [
        _HotZone(570, 366, 710, 408, 1, "Login button"),
    ],
    # Screen 1 (home) — Coverage tab advances to coverage
    1: [
        _HotZone(162, 135, 322, 173, 2, "Coverage tab"),
    ],
    # Screen 2 (coverage) — no auto-advance; F8 or wrap
    2: [],
}

W, H = 1280, 800


class ScreenPlayer:
    """Tkinter-based mock screen player."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mock Epic — Citrix Viewer")
        self.root.resizable(False, False)
        # Place at top-left so OR absolute coords match pixel coords.
        self.root.geometry(f"{W}x{H}+0+0")

        self._screen_idx = 0
        self._images: list[Image.Image] = []
        self._tk_images: list[ImageTk.PhotoImage] = []

        # Canvas
        self.canvas = tk.Canvas(root, width=W, height=H, bd=0, highlightthickness=0)
        self.canvas.pack()

        # Status bar (outside the 1280×800 area — drawn on canvas for info)
        self._status_var = tk.StringVar(value="Screen: login | F8=next | Esc=quit")

        # Load all screens up front
        self._load_screens()

        # Bindings
        root.bind("<F8>", self._on_f8)
        root.bind("<Escape>", lambda _e: root.destroy())
        self.canvas.bind("<Button-1>", self._on_click)

        # Initial render
        self._show_current()

        # Retina warning
        self._check_retina()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_screens(self) -> None:
        for path in _SCREEN_FILES:
            if not path.exists():
                print(
                    f"WARNING: {path} not found — run generate_mock_screens.py first",
                    file=sys.stderr,
                )
                # Create a blank placeholder so the player still starts
                img = Image.new("RGB", (W, H), (200, 50, 50))
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                draw.text((40, 380), f"MISSING: {path.name}\nRun generate_mock_screens.py",
                          fill=(255, 255, 255))
            else:
                img = Image.open(path).convert("RGB")
                # Resize if the PNG was generated at a different size
                if img.size != (W, H):
                    img = img.resize((W, H), Image.LANCZOS)
            self._images.append(img)
            self._tk_images.append(ImageTk.PhotoImage(img))

    def _check_retina(self) -> None:
        # On macOS Retina, tkinter reports logical pixels; physical = 2×.
        # The framework uses pyautogui which operates in physical pixels.
        try:
            scale = self.root.tk.call("tk", "scaling")
            if float(scale) > 1.5:
                print(
                    "INFO: Retina display detected (tk scaling={:.1f}).  "
                    "Set PYAUTOGUI_SCALE=2 or run at 1x resolution.".format(float(scale))
                )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_current(self) -> None:
        idx = self._screen_idx
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_images[idx])
        # Overlay hot-zone outlines (semi-transparent via stipple)
        self.canvas.delete("hotzone")
        for hz in _HOT_ZONES.get(idx, []):
            self.canvas.create_rectangle(
                hz.x0, hz.y0, hz.x1, hz.y1,
                outline="yellow", width=2, dash=(4, 4), tags="hotzone",
            )
            self.canvas.create_text(
                (hz.x0 + hz.x1) // 2, hz.y0 - 6,
                text=hz.label, fill="yellow", font=("Arial", 9), tags="hotzone",
            )
        name = _SCREEN_NAMES[idx]
        self.root.title(f"Mock Epic — Citrix Viewer  [{name}]")
        print(f"[screen_player] showing screen {idx}: {name}")

    def _advance_to(self, target: int) -> None:
        self._screen_idx = target % len(_SCREEN_FILES)
        self._show_current()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_f8(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._advance_to(self._screen_idx + 1)

    def _on_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        x, y = event.x, event.y
        print(f"[screen_player] click at ({x}, {y})  screen={_SCREEN_NAMES[self._screen_idx]}")
        for hz in _HOT_ZONES.get(self._screen_idx, []):
            if hz.x0 <= x <= hz.x1 and hz.y0 <= y <= hz.y1:
                print(f"[screen_player] hot zone '{hz.label}' triggered → screen {hz.target_screen}")
                self._advance_to(hz.target_screen)
                return


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    app = ScreenPlayer(root)
    print("Screen player started.  F8=next screen | Esc=quit | click hot zones to advance.")
    root.mainloop()


if __name__ == "__main__":
    main()
