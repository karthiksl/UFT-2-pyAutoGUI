"""Generate synthetic PNG mock screens for the SAMPLE_TEST_000001 dry-run.

Run once before running the screen_player or the flow test:

    python fixtures/sample_uft/generate_mock_screens.py

Outputs
-------
fixtures/sample_uft/screens/
    app_frame.png          1280×800  outer Citrix session chrome
    login.png              1280×800  login screen composited onto app_frame
    home.png               1280×800  home screen with MRN banner
    coverage.png           1280×800  coverage screen with effective date

automation/assets/images/sample/
    frame_titlebar.png             anchor — Citrix chrome title bar strip
    login_header_banner.png        anchor — "Mock Epic" header
    login_username_input.png       object — username field label+box
    login_password_input.png       object — password field label+box
    login_button.png               object — Login button
    home_banner_label.png          anchor — patient MRN banner
    home_coverage_tab.png          object — Coverage tab
    coverage_header.png            anchor — "Coverage" screen header
    coverage_effective_date_field.png  object — effective date value

All coordinates are relative to the 1280×800 screen.  The object PNGs are
tight crops of the region declared in sample_or.yaml — used by
core/finder.py for template matching.

Design choices
--------------
* No random data — pixel values are computed deterministically.
* DejaVuSans is the preferred font; falls back to the Pillow default if
  DejaVuSans is not installed (macOS/Linux both have it, or use
  ImageFont.load_default()).
* All colours are CSS-style hex literals so they are easy to adjust.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from any working directory
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCREENS_DIR = Path(__file__).resolve().parent / "screens"
_ASSETS_DIR = _REPO_ROOT / "automation" / "assets" / "images" / "sample"

_SCREENS_DIR.mkdir(parents=True, exist_ok=True)
_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Pillow import guard
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow is required.  pip install Pillow", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants — screen geometry
# ---------------------------------------------------------------------------
W, H = 1280, 800
TITLEBAR_H = 36          # Citrix chrome title bar height
CONTENT_TOP = TITLEBAR_H # content area starts here

# Colour palette
C_CITRIX_BAR = (0, 94, 184)       # Citrix blue
C_CITRIX_TEXT = (255, 255, 255)
C_APP_BG = (240, 243, 246)        # Epic-ish light grey
C_HEADER_BG = (0, 64, 128)        # Epic navy banner
C_HEADER_TEXT = (255, 255, 255)
C_FIELD_BG = (255, 255, 255)
C_FIELD_BORDER = (120, 130, 145)
C_BUTTON_BG = (0, 112, 192)
C_BUTTON_TEXT = (255, 255, 255)
C_TAB_ACTIVE = (0, 112, 192)
C_TAB_INACTIVE = (180, 190, 200)
C_TAB_TEXT = (255, 255, 255)
C_BODY_TEXT = (30, 30, 30)
C_MRN_BANNER = (0, 50, 100)
C_COVERAGE_BG = (250, 252, 255)
C_DATE_VALUE = (20, 20, 20)


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a TrueType font at *size* pt; fall back to bitmap default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf".format("-Bold" if bold else ""),
        "/usr/share/fonts/dejavu/DejaVuSans{}.ttf".format("-Bold" if bold else ""),
        "/System/Library/Fonts/Supplemental/Arial{}.ttf".format(" Bold" if bold else ""),
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Shared drawing helpers
# ---------------------------------------------------------------------------
def _draw_citrix_titlebar(draw: ImageDraw.ImageDraw, title: str = "Mock Epic — Citrix Viewer") -> None:
    draw.rectangle([0, 0, W - 1, TITLEBAR_H - 1], fill=C_CITRIX_BAR)
    f = _font(13, bold=True)
    draw.text((12, 8), title, font=f, fill=C_CITRIX_TEXT)
    # Traffic-light style close / minimise dots (decorative)
    for i, col in enumerate([(220, 80, 60), (230, 180, 60), (80, 195, 80)]):
        cx = W - 24 - i * 22
        draw.ellipse([cx - 7, 11, cx + 7, 25], fill=col)


def _draw_epic_header(draw: ImageDraw.ImageDraw, title: str) -> None:
    draw.rectangle([0, TITLEBAR_H, W - 1, TITLEBAR_H + 55], fill=C_HEADER_BG)
    f = _font(20, bold=True)
    draw.text((20, TITLEBAR_H + 14), title, font=f, fill=C_HEADER_TEXT)


def _draw_field(
    draw: ImageDraw.ImageDraw,
    label: str,
    x: int,
    y: int,
    width: int = 300,
    height: int = 36,
    value: str = "",
) -> tuple[int, int, int, int]:
    """Draw a labelled input field; return (x, y, x+width, y+height) region."""
    lf = _font(13)
    draw.text((x, y - 20), label, font=lf, fill=C_BODY_TEXT)
    draw.rectangle([x, y, x + width, y + height], fill=C_FIELD_BG, outline=C_FIELD_BORDER, width=2)
    if value:
        vf = _font(13)
        draw.text((x + 8, y + 9), value, font=vf, fill=C_BODY_TEXT)
    return (x, y, x + width, y + height)


def _draw_button(
    draw: ImageDraw.ImageDraw,
    label: str,
    x: int,
    y: int,
    width: int = 120,
    height: int = 38,
) -> tuple[int, int, int, int]:
    draw.rectangle([x, y, x + width, y + height], fill=C_BUTTON_BG, outline=(0, 80, 160), width=2)
    f = _font(14, bold=True)
    # Centre text
    bbox = draw.textbbox((0, 0), label, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (width - tw) // 2, y + (height - th) // 2), label, font=f, fill=C_BUTTON_TEXT)
    return (x, y, x + width, y + height)


def _new_screen(bg: tuple[int, int, int] = C_APP_BG) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    return img, draw


def _crop_and_save(img: Image.Image, region: tuple[int, int, int, int], dest: Path) -> None:
    """Crop *region* (x0,y0,x1,y1) from *img* and save to *dest*."""
    cropped = img.crop(region)
    cropped.save(dest)
    print(f"  crop  → {dest.relative_to(_REPO_ROOT)}")


# ===========================================================================
# Screen 0 — app_frame  (empty Citrix chrome, no Epic content)
# ===========================================================================
def build_app_frame() -> Image.Image:
    img, draw = _new_screen(C_APP_BG)
    _draw_citrix_titlebar(draw)
    # Citrix toolbar strip below title bar
    draw.rectangle([0, TITLEBAR_H, W - 1, TITLEBAR_H + 20], fill=(210, 215, 220))
    f = _font(11)
    draw.text((8, TITLEBAR_H + 4), "File  View  Preferences  Help", font=f, fill=(60, 60, 60))
    return img


# ===========================================================================
# Screen 1 — login
# ===========================================================================
def build_login(frame: Image.Image) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    img = frame.copy()
    draw = ImageDraw.Draw(img)

    # Epic header
    _draw_epic_header(draw, "Mock Epic")

    # Sub-header / login card background
    card_x, card_y, card_w, card_h = 390, TITLEBAR_H + 80, 500, 340
    draw.rectangle([card_x, card_y, card_x + card_w, card_y + card_h],
                   fill=(255, 255, 255), outline=(180, 190, 200), width=2)

    # "Sign In" title inside card
    f_title = _font(18, bold=True)
    draw.text((card_x + 170, card_y + 18), "Sign In", font=f_title, fill=C_BODY_TEXT)

    # Username field
    uf_region = _draw_field(draw, "Username", card_x + 60, card_y + 80, width=380)
    # Password field
    pf_region = _draw_field(draw, "Password", card_x + 60, card_y + 155, width=380)
    # Draw password dots
    draw.text((card_x + 68, card_y + 163), "••••••••", font=_font(14), fill=(80, 80, 80))

    # Login button
    btn_region = _draw_button(draw, "Login", card_x + 180, card_y + 250, width=140, height=42)

    # Divider / version line
    draw.text((card_x + 100, card_y + 305), "Mock Epic v24.1 — Sample Fixture",
              font=_font(10), fill=(140, 150, 160))

    regions = {
        "header_banner": (0, TITLEBAR_H, W, TITLEBAR_H + 55),
        "username_field": (uf_region[0] - 2, uf_region[1] - 22, uf_region[2] + 2, uf_region[3] + 2),
        "password_field": (pf_region[0] - 2, pf_region[1] - 22, pf_region[2] + 2, pf_region[3] + 2),
        "login_button": btn_region,
    }
    return img, regions


# ===========================================================================
# Screen 2 — home
# ===========================================================================
def build_home(frame: Image.Image, mrn: str = "1234567") -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    img = frame.copy()
    draw = ImageDraw.Draw(img)

    # Epic header
    _draw_epic_header(draw, "Mock Epic — Patient Hub")

    # Patient MRN banner (below header)
    banner_y = TITLEBAR_H + 55
    banner_h = 44
    draw.rectangle([0, banner_y, W - 1, banner_y + banner_h], fill=C_MRN_BANNER)
    f_mrn = _font(16, bold=True)
    mrn_text = f"Rivera, Maria    MRN: {mrn}    DOB: 03/15/1982    Plan: Mock HMO"
    draw.text((20, banner_y + 11), mrn_text, font=f_mrn, fill=(255, 255, 255))

    # Tab bar
    tab_y = banner_y + banner_h
    tab_h = 38
    tabs = ["Summary", "Coverage", "Demographics", "Notes"]
    tab_x = 0
    tab_regions: dict[str, tuple[int, int, int, int]] = {}
    for tab in tabs:
        tab_w = 160
        is_active = tab == "Coverage"
        fill = C_TAB_ACTIVE if is_active else C_TAB_INACTIVE
        draw.rectangle([tab_x, tab_y, tab_x + tab_w, tab_y + tab_h], fill=fill)
        f_tab = _font(13, bold=is_active)
        bbox = draw.textbbox((0, 0), tab, font=f_tab)
        tw = bbox[2] - bbox[0]
        draw.text((tab_x + (tab_w - tw) // 2, tab_y + 10), tab, font=f_tab, fill=C_TAB_TEXT)
        tab_regions[tab.lower()] = (tab_x, tab_y, tab_x + tab_w, tab_y + tab_h)
        tab_x += tab_w + 2

    # Content area placeholder
    content_top = tab_y + tab_h + 10
    draw.text((40, content_top + 20), "Recent Activity", font=_font(14, bold=True), fill=C_BODY_TEXT)
    draw.text((40, content_top + 50), "No pending actions.", font=_font(12), fill=(100, 100, 100))

    regions = {
        "header_banner": (0, TITLEBAR_H, W, TITLEBAR_H + 55),
        "banner_label": (0, banner_y, W, banner_y + banner_h),
        "coverage_tab": tab_regions["coverage"],
    }
    return img, regions


# ===========================================================================
# Screen 3 — coverage
# ===========================================================================
def build_coverage(frame: Image.Image, effective_date: str = "01/01/2026") -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    img = frame.copy()
    draw = ImageDraw.Draw(img)

    # Epic header
    _draw_epic_header(draw, "Mock Epic — Coverage")

    # Patient banner (slim)
    banner_y = TITLEBAR_H + 55
    draw.rectangle([0, banner_y, W - 1, banner_y + 30], fill=(0, 40, 80))
    draw.text((20, banner_y + 7), "Rivera, Maria  |  MRN: 1234567",
              font=_font(12), fill=(200, 220, 240))

    # Coverage header section
    header_y = banner_y + 38
    draw.rectangle([20, header_y, W - 20, header_y + 50],
                   fill=C_COVERAGE_BG, outline=(180, 190, 200), width=1)
    f_cov = _font(18, bold=True)
    draw.text((30, header_y + 12), "Coverage", font=f_cov, fill=C_HEADER_BG)

    # Fields
    field_top = header_y + 70

    # Effective Date (label + value as a static read-only field)
    draw.text((30, field_top), "Effective Date", font=_font(13), fill=(80, 80, 80))
    date_box_y = field_top + 22
    date_box = (30, date_box_y, 230, date_box_y + 36)
    draw.rectangle(date_box, fill=(248, 249, 251), outline=C_FIELD_BORDER, width=2)
    draw.text((38, date_box_y + 8), effective_date, font=_font(14, bold=True), fill=C_DATE_VALUE)

    draw.text((260, field_top), "Plan Name", font=_font(13), fill=(80, 80, 80))
    draw.rectangle([260, date_box_y, 600, date_box_y + 36],
                   fill=(248, 249, 251), outline=C_FIELD_BORDER, width=2)
    draw.text((268, date_box_y + 8), "Mock HMO Gold", font=_font(14), fill=C_DATE_VALUE)

    draw.text((30, field_top + 70), "Coverage Type", font=_font(13), fill=(80, 80, 80))
    draw.rectangle([30, date_box_y + 75, 230, date_box_y + 111],
                   fill=(248, 249, 251), outline=C_FIELD_BORDER, width=2)
    draw.text((38, date_box_y + 84), "Medical", font=_font(14), fill=C_DATE_VALUE)

    draw.text((260, field_top + 70), "Status", font=_font(13), fill=(80, 80, 80))
    draw.rectangle([260, date_box_y + 75, 460, date_box_y + 111],
                   fill=(248, 249, 251), outline=C_FIELD_BORDER, width=2)
    draw.text((268, date_box_y + 84), "Active", font=_font(14, bold=True), fill=(0, 140, 60))

    regions = {
        "header_banner": (0, TITLEBAR_H, W, TITLEBAR_H + 55),
        "coverage_header": (20, header_y, W - 20, header_y + 50),
        "effective_date_field": (30, field_top - 2, 232, date_box_y + 38),
    }
    return img, regions


# ===========================================================================
# Titlebar anchor crop (shared across screens)
# ===========================================================================
def _save_titlebar_anchor(frame: Image.Image) -> None:
    # Crop just the title bar text region (left ~400 px, full height)
    _crop_and_save(frame, (0, 0, 400, TITLEBAR_H), _ASSETS_DIR / "frame_titlebar.png")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    print("Generating mock screens …")

    # -----------------------------------------------------------------------
    # Build the base Citrix frame
    # -----------------------------------------------------------------------
    frame = build_app_frame()
    frame_path = _SCREENS_DIR / "app_frame.png"
    frame.save(frame_path)
    print(f"  saved → {frame_path.relative_to(_REPO_ROOT)}")
    _save_titlebar_anchor(frame)

    # -----------------------------------------------------------------------
    # Login screen
    # -----------------------------------------------------------------------
    login_img, login_regions = build_login(frame)
    login_path = _SCREENS_DIR / "login.png"
    login_img.save(login_path)
    print(f"  saved → {login_path.relative_to(_REPO_ROOT)}")

    _crop_and_save(login_img, login_regions["header_banner"],
                   _ASSETS_DIR / "login_header_banner.png")
    _crop_and_save(login_img, login_regions["username_field"],
                   _ASSETS_DIR / "login_username_input.png")
    _crop_and_save(login_img, login_regions["password_field"],
                   _ASSETS_DIR / "login_password_input.png")
    _crop_and_save(login_img, login_regions["login_button"],
                   _ASSETS_DIR / "login_button.png")

    # -----------------------------------------------------------------------
    # Home screen (MRN = 1234567 matches SAMPLE-1 row)
    # -----------------------------------------------------------------------
    home_img, home_regions = build_home(frame, mrn="1234567")
    home_path = _SCREENS_DIR / "home.png"
    home_img.save(home_path)
    print(f"  saved → {home_path.relative_to(_REPO_ROOT)}")

    _crop_and_save(home_img, home_regions["banner_label"],
                   _ASSETS_DIR / "home_banner_label.png")
    _crop_and_save(home_img, home_regions["coverage_tab"],
                   _ASSETS_DIR / "home_coverage_tab.png")

    # -----------------------------------------------------------------------
    # Coverage screen (effective date = 01/01/2026)
    # -----------------------------------------------------------------------
    cov_img, cov_regions = build_coverage(frame, effective_date="01/01/2026")
    cov_path = _SCREENS_DIR / "coverage.png"
    cov_img.save(cov_path)
    print(f"  saved → {cov_path.relative_to(_REPO_ROOT)}")

    _crop_and_save(cov_img, cov_regions["coverage_header"],
                   _ASSETS_DIR / "coverage_header.png")
    _crop_and_save(cov_img, cov_regions["effective_date_field"],
                   _ASSETS_DIR / "coverage_effective_date_field.png")

    print("\nDone.  All PNGs written.")
    print(f"  Screens  : {_SCREENS_DIR}")
    print(f"  OR assets: {_ASSETS_DIR}")


if __name__ == "__main__":
    main()
