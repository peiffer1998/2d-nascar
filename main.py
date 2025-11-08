import json
import math
import os
import random
import re
from collections import defaultdict
from dataclasses import dataclass, replace

import pygame

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
CUP21_FOLDER = "cup21"
CUP21_MANIFEST = os.path.join(CUP21_FOLDER, "cup21.txt")
CAR_REFERENCE_LENGTH = 180
LANE_CHANGE_COOLDOWN = 0.18
SPEED_RIBBON_COUNT = 28
HUD_ALPHA = 230
ROLLING_DURATION = 5.0
START_LINE_OFFSET = 190
SPEED_SCALE = 3.8  # simulation units per MPH
ROLLING_START_MIN_MPH = 110
ROLLING_START_MAX_MPH = 200
CONTROLLED_BASE_MPH = 200
BRAKE_MPH = 120
TURN_PENALTY_MAX = 34
SHOW_LANE_GUIDES = False
TRACK_TOP_WALL_PCT = 0.075
TRACK_DOUBLE_YELLOW_PCT = 0.615
TRACK_APRON_PCT = 0.725
TRACK_GROOVE_OFFSET = 0.08
TRACK_GROOVE_THICK = 0.035
# --- UI layout (DM2-style) ---
TOP_BAR_HEIGHT = 72
HUD_BLOCK_HEIGHT = 120
LEFT_DRAFT_WIDTH = 84
LEFT_DRAFT_EXTRA = 18
HUD_BOTTOM_MARGIN = 12
SEGMENT_COUNT = 20
SEGMENT_HEIGHT = 16
SEGMENT_GAP = 6
TICK_COUNT = 18
# --- UI (TITLE) ---
TITLE_BUTTONS = ("Quick Race", "Settings", "Exit")
BUTTON_W, BUTTON_H = 320, 68
BUTTON_GAP = 18

# --- Quick Race defaults ---
DEFAULT_QUICK_RACE_PRESET = "Cup21 Draft Oval"
DEFAULT_FIELD_SIZE = 43  # keep 43-car feel by default
GREEN_FLASH_TIME = 1.25  # seconds "GREEN!" banner after control unlock
QUICK_RACE_LANE_WIDTH = 96.0
QUICK_RACE_LANE_SPACING = 12.0
QUICK_RACE_ROW_GAP = 16.0
QUICK_RACE_PACK_ROWS = 22
QUICK_RACE_PLAYER_ROW = 18
QUICK_RACE_PLAYER_LANE = 0
QUICK_RACE_ROW_JITTER = 0.45

# --- Collisions & lane safety ---
COLLISION_GAP = 14  # min spacing between cars in same lane (~half the contact threshold)
CRASH_REL_MPH = 24  # closing rate above this => crash
LANE_SAFETY_DISTANCE = 120.0  # block lane change if a car is within ± this
# Derived: units/sec to compare with speeds
CRASH_REL_UNITS = CRASH_REL_MPH * SPEED_SCALE

MANUFACTURER_COLORS = {
    "CHV": (222, 60, 54),
    "FRD": (78, 152, 240),
    "TYT": (250, 170, 44),
    "TYO": (250, 170, 44),
    "DGE": (200, 70, 180),
}

ROLE_FLAVOR = {
    "Closer": "Late run ace",
    "Blocker": "Defensive wall",
    "Strategist": "Setup savant",
    "Dominator": "Controls the pack",
    "Intimidator": "Aggressive edge",
    "Rookie": "Learning curve",
}


@dataclass
class TrackPreset:
    name: str
    lane_count: int
    lane_width: float
    lane_spacing: float
    pack_rows: int
    row_gap: float
    laps: int
    tagline: str
    field_size: int | None = None
    formation_lanes: list[int] | None = None


@dataclass
class DriverInfo:
    car_num: str
    driver_name: str
    team: str
    manufacturer: str
    rarity: int
    role: str
    sprites: list
    accent: tuple[int, int, int]


class SpeedRibbon:
    def __init__(self, track_bounds):
        self.track_bounds = track_bounds
        self.reset(random.uniform(0, SCREEN_WIDTH))

    def reset(self, start_x=None):
        top, bottom = self.track_bounds
        self.x = start_x if start_x is not None else SCREEN_WIDTH + random.uniform(40, 220)
        self.y = random.uniform(top + 12, bottom - 12)
        self.length = random.uniform(90, 220)
        self.width = random.uniform(3, 6)
        self.speed = random.uniform(360, 820)
        self.alpha = random.randint(40, 110)

    def update(self, delta, sim_player_speed):
        self.x -= (self.speed + sim_player_speed * 0.45) * delta
        if self.x + self.length < -120:
            self.reset()

    def draw(self, surface):
        stripe = pygame.Surface((self.length, self.width), pygame.SRCALPHA)
        color = (210, 235, 255, int(self.alpha))
        pygame.draw.rect(stripe, color, stripe.get_rect(), border_radius=6)
        surface.blit(stripe, (self.x, self.y))


TRACK_PRESETS = [
    TrackPreset(
        "Cup21 Draft Oval",
        lane_count=3,
        lane_width=218.0,
        lane_spacing=118.0,
        pack_rows=23,
        row_gap=56.0,
        laps=12,
        tagline="Three-lane Daytona vibe with a 43-car formation.",
        field_size=43,
        formation_lanes=[0, 2],
    ),
    TrackPreset(
        "3-Lane Oval",
        lane_count=3,
        lane_width=210.0,
        lane_spacing=220.0,
        pack_rows=6,
        row_gap=70.0,
        laps=10,
        tagline="Wide middle lane, tight draft funnels.",
    ),
    TrackPreset(
        "Superspeedway 5",
        lane_count=5,
        lane_width=200.0,
        lane_spacing=200.0,
        pack_rows=8,
        row_gap=65.0,
        laps=8,
        tagline="Packed, relentless pace with extra lanes.",
    ),
    TrackPreset(
        "Drafting Tri-Oval",
        lane_count=4,
        lane_width=205.0,
        lane_spacing=210.0,
        pack_rows=5,
        row_gap=80.0,
        laps=6,
        tagline="Triangle drafting that rewards timing.",
    ),
]


def move_toward(value, target, step):
    if value < target:
        return min(value + step, target)
    if value > target:
        return max(value - step, target)
    return value


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def parse_rarity(raw_value: str) -> int:
    try:
        return clamp(int(raw_value), 1, 5)
    except (TypeError, ValueError):
        return 1


def create_placeholder_sprite(color=(90, 130, 222)):
    surf = pygame.Surface((160, 72), pygame.SRCALPHA)
    body = pygame.Rect(10, 10, 140, 52)
    pygame.draw.rect(surf, color, body, border_radius=20)
    pygame.draw.rect(surf, (20, 24, 32), body, width=3, border_radius=20)
    canopy = pygame.Rect(28, 20, 54, 32)
    pygame.draw.rect(surf, (200, 230, 255), canopy, border_radius=10)
    pygame.draw.rect(surf, (255, 255, 255), (body.left + 8, body.bottom - 18, 16, 8))
    pygame.draw.rect(surf, (255, 255, 255), (body.right - 24, body.bottom - 18, 16, 8))
    return surf


def prepare_car_sprite(image: pygame.Surface):
    sprite = image.convert_alpha()
    width, height = sprite.get_size()
    largest = max(width, height) or 1
    scale = CAR_REFERENCE_LENGTH / largest
    new_size = (int(width * scale), int(height * scale))
    sprite = pygame.transform.smoothscale(sprite, new_size)
    return sprite


def derive_accent_color(surface: pygame.Surface):
    try:
        avg = pygame.transform.average_color(surface)
    except pygame.error:
        avg = (200, 200, 200)
    avg_rgb = avg[:3] if len(avg) >= 3 else avg
    r, g, b = avg_rgb
    return clamp(r + 20, 80, 255), clamp(g + 10, 80, 255), clamp(b + 5, 80, 255)


def manufacturer_accent(code: str):
    return MANUFACTURER_COLORS.get(code.upper(), (180, 200, 230))


def load_cup21_drivers():
    if not os.path.isfile(CUP21_MANIFEST):
        return []
    try:
        with open(CUP21_MANIFEST, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    asset_map: dict[str, list[str]] = defaultdict(list)
    if os.path.isdir(CUP21_FOLDER):
        for entry in os.listdir(CUP21_FOLDER):
            if not entry.lower().endswith(".png"):
                continue
            match = re.match(r"cup21-(\d+)", entry.lower())
            if not match:
                continue
            asset_map[match.group(1)].append(os.path.join(CUP21_FOLDER, entry))
    for asset_list in asset_map.values():
        asset_list.sort()
    drivers: list[DriverInfo] = []
    for driver_data in manifest.get("drivers", []):
        car_num = driver_data.get("carNum", "").strip()
        if not car_num:
            continue
        sprites = []
        for asset_path in asset_map.get(car_num, []):
            try:
                image = pygame.image.load(asset_path)
                sprites.append(prepare_car_sprite(image))
            except pygame.error:
                continue
        if not sprites:
            sprites = [create_placeholder_sprite()]
        accent = manufacturer_accent(driver_data.get("carManufacturer", ""))
        accent = tuple(
            clamp((accent[i] + derive_accent_color(sprites[0])[i]) // 2, 70, 255) for i in range(3)
        )
        drivers.append(
            DriverInfo(
                car_num=car_num,
                driver_name=driver_data.get("carDriver", "Unknown").strip() or "Unknown",
                team=driver_data.get("carTeam", "Team").strip() or "Team",
                manufacturer=driver_data.get("carManufacturer", "Custom").strip() or "Custom",
                rarity=parse_rarity(driver_data.get("carRarity", "1")),
                role=driver_data.get("carType", "Closer").strip() or "Closer",
                sprites=sprites,
                accent=accent,
            )
        )
    return drivers


def create_default_driver():
    sprite = create_placeholder_sprite()
    accent = derive_accent_color(sprite)
    return DriverInfo("00", "Player", "Home Team", "Custom", 1, "Closer", [sprite], accent)


def build_lane_positions(lane_count, lane_height, lane_spacing):
    if lane_count <= 0:
        return []
    total_height = lane_count * lane_height + max(0, (lane_count - 1) * lane_spacing)
    top = SCREEN_HEIGHT / 2 - total_height / 2
    step = lane_height + lane_spacing
    return [top + step * i + lane_height / 2 for i in range(lane_count)]


def lane_center_at(lane_positions, lane_value):
    if not lane_positions:
        return SCREEN_HEIGHT / 2
    lane_value = clamp(lane_value, 0, len(lane_positions) - 1)
    low = int(math.floor(lane_value))
    high = int(math.ceil(lane_value))
    if low == high:
        return lane_positions[low]
    t = lane_value - low
    return lane_positions[low] * (1 - t) + lane_positions[high] * t


def compute_track_bounds(lane_positions, lane_height, lane_spacing):
    if not lane_positions:
        return 0, SCREEN_HEIGHT
    base_y = lane_positions[0] - lane_height / 2
    top = int(base_y - lane_spacing * 0.6 - 26)
    bottom = int(lane_positions[-1] + lane_height / 2 + lane_spacing * 0.6 + 26)
    return top, bottom


def build_speed_ribbons(track_bounds):
    return [SpeedRibbon(track_bounds) for _ in range(SPEED_RIBBON_COUNT)]


def draw_asphalt_background(surface):
    width, height = surface.get_size()
    gradient = pygame.Surface((width, height))
    for y in range(height):
        ratio = y / max(1, height - 1)
        if ratio < 0.6:
            t = ratio / 0.6
            start = (106, 110, 120)
            end = (92, 96, 105)
        else:
            t = (ratio - 0.6) / 0.4
            start = (92, 96, 105)
            end = (88, 92, 101)
        r = int(start[0] + (end[0] - start[0]) * t)
        g = int(start[1] + (end[1] - start[1]) * t)
        b = int(start[2] + (end[2] - start[2]) * t)
        pygame.draw.line(gradient, (r, g, b), (0, y), (width, y))
    surface.blit(gradient, (0, 0))
    speckle = pygame.Surface((width, height), pygame.SRCALPHA)
    step = 4
    for y in range(0, height, step):
        for x in range(0, width, step):
            v = (x * 73856093 ^ y * 19349663) & 15
            if v == 0:
                continue
            alpha = int((v / 15) * 60)
            speckle.fill((30, 30, 30, alpha), (x, y, step, step))
    surface.blit(speckle, (0, 0))


def draw_stands_section(surface, track_top):
    stand_top = max(0, track_top - 60)
    pygame.draw.rect(surface, (183, 188, 199), (0, stand_top, SCREEN_WIDTH, 10))
    pygame.draw.rect(surface, (140, 146, 160), (0, stand_top + 10, SCREEN_WIDTH, 8))
    limit = max(0, stand_top - 6)
    for y in range(0, limit, 4):
        for x in range(0, SCREEN_WIDTH, 6):
            r = (x * 1103515245 + y * 12345) & 0xFFFFFFFF
            if (r & 7) != 0:
                continue
            colors = [
                (231, 76, 60),
                (52, 152, 219),
                (241, 196, 15),
                (46, 204, 113),
                (236, 240, 241),
                (155, 89, 182),
            ]
            color = colors[r % len(colors)]
            surface.fill(color, (x, y, 2, 2))


def draw_racing_surface(surface, track_rect, lane_positions):
    if track_rect.height <= 0:
        return
    width = track_rect.width
    height = track_rect.height
    track_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(height):
        ratio = y / max(1, height - 1)
        shade = int(70 + ratio * 40)
        pygame.draw.line(track_surface, (shade, shade, min(shade + 12, 255)), (0, y), (width, y))
    surface.blit(track_surface, track_rect.topleft)
    y_yellow = clamp(track_rect.top + int(height * TRACK_DOUBLE_YELLOW_PCT), track_rect.top + 4, track_rect.bottom - 4)
    pygame.draw.rect(surface, (246, 194, 28), (0, y_yellow - 4, width, 3))
    pygame.draw.rect(surface, (246, 194, 28), (0, y_yellow + 3, width, 3))
    groove_y = max(track_rect.top + 4, y_yellow - int(height * TRACK_GROOVE_OFFSET))
    groove_height = max(2, int(height * TRACK_GROOVE_THICK))
    groove_height = min(groove_height, max(1, track_rect.bottom - groove_y))
    groove_surface = pygame.Surface((width, groove_height), pygame.SRCALPHA)
    for gy in range(groove_height):
        t = gy / max(1, groove_height - 1)
        if t < 0.2:
            alpha = int(18 * (t / 0.2))
        elif t > 0.8:
            alpha = int(18 * ((1 - t) / 0.2))
        else:
            alpha = 18
        pygame.draw.line(groove_surface, (0, 0, 0, alpha), (0, gy), (width, gy))
    surface.blit(groove_surface, (0, groove_y))
    apron_y = clamp(track_rect.top + int(height * TRACK_APRON_PCT), track_rect.top + 4, track_rect.bottom)
    pygame.draw.rect(surface, (232, 236, 242), (0, apron_y, width, 3))
    apron_top = apron_y + 3
    if apron_top < track_rect.bottom:
        apron_height = track_rect.bottom - apron_top
        apron_surface = pygame.Surface((width, apron_height), pygame.SRCALPHA)
        start_color = (29, 111, 49)
        end_color = (24, 90, 41)
        for ay in range(apron_height):
            t = ay / max(1, apron_height - 1)
            r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
            pygame.draw.line(apron_surface, (r, g, b), (0, ay), (width, ay))
        surface.blit(apron_surface, (0, apron_top))
    if SHOW_LANE_GUIDES and lane_positions:
        guide_color = (230, 238, 246)
        dash_len = 12
        dash_gap = 8
        for lane_y in lane_positions:
            if lane_y < track_rect.top or lane_y > track_rect.bottom:
                continue
            y_pos = int(lane_y)
            x = 0
            while x < width:
                x_end = min(width, x + dash_len)
                pygame.draw.line(surface, guide_color, (x, y_pos), (x_end, y_pos), 2)
                x += dash_len + dash_gap


def draw_track(surface, lane_positions, lane_height, lane_spacing, lane_count, scroll, ribbons):
    draw_asphalt_background(surface)
    track_top, track_bottom = compute_track_bounds(lane_positions, lane_height, lane_spacing)
    height = max(48, track_bottom - track_top)
    track_rect = pygame.Rect(0, track_top, SCREEN_WIDTH, height)
    draw_stands_section(surface, track_rect.top)
    draw_racing_surface(surface, track_rect, lane_positions)
    for ribbon in ribbons:
        ribbon.draw(surface)
    return track_rect


def build_leader_entries(ai_cars, sim_speed, limit=6):
    entries = []
    sorted_cars = sorted(ai_cars, key=lambda c: c.distance, reverse=True)
    effective_speed = max(sim_speed, 1.0)
    for idx, car in enumerate(sorted_cars[:limit]):
        gap_secs = abs(car.distance) / effective_speed
        prefix = "+" if car.distance >= 0 else "-"
        entries.append(
            {
                "pos": idx + 1,
                "car_num": car.driver.car_num,
                "name": car.driver.driver_name,
                "gap": f"{prefix}{gap_secs:0.3f}",
            }
        )
    if not entries:
        entries = [
            {"pos": i + 1, "car_num": "--", "name": "None", "gap": "+0.000"} for i in range(limit)
        ]
    return entries


def draw_dm2_ui(surface, fonts, data):
    font, font_large, font_small = fonts
    panel_color = (17, 21, 31)
    border_color = (90, 99, 120)
    track_text_color = (240, 245, 255)
    lap_box_color = (54, 234, 104)
    lap_box_border = (30, 164, 74)
    hud_color = (11, 15, 22)
    hud_border = (90, 99, 120)
    caret_color = (196, 68, 68)
    pause_color = (212, 60, 60)

    top_rect = pygame.Rect(0, 0, SCREEN_WIDTH, TOP_BAR_HEIGHT)
    pygame.draw.rect(surface, panel_color, top_rect)
    pygame.draw.rect(surface, border_color, top_rect, 2)

    brand_rect = pygame.Rect(12, 12, 200, TOP_BAR_HEIGHT - 24)
    pygame.draw.rect(surface, (43, 47, 58), brand_rect, border_radius=8)
    pygame.draw.rect(surface, (61, 69, 91), brand_rect, 2, border_radius=8)
    title_rect = pygame.Rect(brand_rect.left + 4, brand_rect.top + 2, brand_rect.width - 8, 18)
    pygame.draw.rect(surface, (225, 65, 47), title_rect, border_radius=4)
    pygame.draw.rect(surface, (160, 39, 31), title_rect, 2, border_radius=4)
    title_text = font_small.render("DRAFTMASTER 2", True, (25, 12, 12))
    surface.blit(
        title_text,
        (title_rect.left + 6, title_rect.top + (title_rect.height - title_text.get_height()) // 2),
    )
    sub_text = font_small.render("ROLLING THUNDER", True, (244, 193, 27))
    surface.blit(
        sub_text,
        (brand_rect.left + 6, title_rect.bottom + 2),
    )

    lap_rect = pygame.Rect(brand_rect.right + 12, 16, 170, TOP_BAR_HEIGHT - 32)
    pygame.draw.rect(surface, lap_box_color, lap_rect, border_radius=6)
    pygame.draw.rect(surface, lap_box_border, lap_rect, 3, border_radius=6)
    lap_text = font_small.render(f"LAP {data['lap']} OF {data['laps_total']}", True, (7, 20, 11))
    surface.blit(
        lap_text,
        (lap_rect.left + 12, lap_rect.top + (lap_rect.height - lap_text.get_height()) // 2),
    )

    track_surface = font_large.render(data["track_name"], True, track_text_color)
    surface.blit(
        track_surface,
        (SCREEN_WIDTH // 2 - track_surface.get_width() // 2, 10),
    )

    control_locked = data.get("control_locked", False)
    if control_locked:
        rolling_text = font_small.render("Rolling start — controls locked", True, (255, 230, 200))
        surface.blit(
            rolling_text,
            (SCREEN_WIDTH // 2 - rolling_text.get_width() // 2, TOP_BAR_HEIGHT + 6),
        )

    caret_size = 40
    pause_size = 40
    button_gap = 12
    buttons_width = caret_size + pause_size + button_gap
    leaders_left = lap_rect.right + 14
    leaders_right = SCREEN_WIDTH - (buttons_width + 18)
    leaders_width = max(160, leaders_right - leaders_left)
    leaders_rect = pygame.Rect(leaders_left, 10, leaders_width, TOP_BAR_HEIGHT - 20)
    pygame.draw.rect(surface, panel_color, leaders_rect)
    pygame.draw.rect(surface, border_color, leaders_rect, 2, border_radius=8)

    if data.get("leaders_collapsed"):
        collapsed = font_small.render("LEADERS COLLAPSED", True, (177, 188, 204))
        surface.blit(
            collapsed,
            (leaders_rect.left + 12, leaders_rect.centery - collapsed.get_height() // 2),
        )
    else:
        entries = data.get("leaders", [])
        if entries:
            entry_width = max(1, leaders_rect.width // len(entries))
            for idx, entry in enumerate(entries):
                entry_x = leaders_rect.left + idx * entry_width + 6
                entry_y = leaders_rect.top + 6
                title = font_small.render(
                    f"{entry['pos']} {entry['car_num']} {entry['name']}", True, track_text_color
                )
                gap = font_small.render(entry["gap"], True, (255, 236, 99))
                surface.blit(title, (entry_x, entry_y))
                surface.blit(gap, (entry_x, entry_y + title.get_height() + 2))

    caret_rect = pygame.Rect(leaders_right + button_gap, 16, caret_size, caret_size)
    pygame.draw.rect(surface, caret_color, caret_rect, border_radius=8)
    pygame.draw.rect(surface, (120, 140, 190), caret_rect, 2, border_radius=8)
    caret_points = [
        (caret_rect.left + 12, caret_rect.top + 14),
        (caret_rect.right - 12, caret_rect.centery),
        (caret_rect.left + 12, caret_rect.bottom - 14),
    ]
    if data.get("leaders_collapsed"):
        caret_points = [
            (caret_rect.right - 12, caret_rect.top + 14),
            (caret_rect.left + 12, caret_rect.centery),
            (caret_rect.right - 12, caret_rect.bottom - 14),
        ]
    pygame.draw.polygon(surface, (255, 255, 255), caret_points)

    pause_rect = pygame.Rect(caret_rect.right + button_gap, 16, pause_size, pause_size)
    pause_fill = pause_color if not data.get("pause_active") else (180, 120, 70)
    pygame.draw.rect(surface, pause_fill, pause_rect, border_radius=8)
    pygame.draw.rect(surface, (120, 140, 190), pause_rect, 2, border_radius=8)
    bar_width = 6
    bar_height = 18
    bar_y = pause_rect.centery - bar_height // 2
    pygame.draw.rect(
        surface,
        (255, 255, 255) if not data.get("pause_active") else (230, 230, 230),
        (pause_rect.left + 10, bar_y, bar_width, bar_height),
        border_radius=2,
    )
    pygame.draw.rect(
        surface,
        (255, 255, 255) if not data.get("pause_active") else (230, 230, 230),
        (pause_rect.right - 10 - bar_width, bar_y, bar_width, bar_height),
        border_radius=2,
    )

    # Segments
    seg_top = SCREEN_HEIGHT - HUD_BLOCK_HEIGHT - 24
    seg_left = int(SCREEN_WIDTH * 0.30)
    seg_right = SCREEN_WIDTH - seg_left
    seg_area = seg_right - seg_left
    seg_width = max(4, int((seg_area - (SEGMENT_COUNT - 1) * SEGMENT_GAP) / SEGMENT_COUNT))
    if data.get("lift_active"):
        on_ratio = 0.22
    elif data.get("brake"):
        on_ratio = 0.36
    else:
        on_ratio = 0.82
    on_count = round(SEGMENT_COUNT * on_ratio)
    for i in range(SEGMENT_COUNT):
        rect = pygame.Rect(
            seg_left + i * (seg_width + SEGMENT_GAP),
            seg_top,
            seg_width,
            SEGMENT_HEIGHT,
        )
        color = (255, 202, 28)
        alpha = 255 if i < on_count else 100
        seg_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        seg_surf.fill((*color, alpha))
        pygame.draw.rect(seg_surf, (*color, 200), seg_surf.get_rect(), border_radius=3)
        surface.blit(seg_surf, rect.topleft)

    # Ticks
    tick_y = seg_top + SEGMENT_HEIGHT + 6
    tick_height = 10
    tick_spacing = seg_area / max(1, TICK_COUNT - 1)
    for i in range(TICK_COUNT):
        tx = int(seg_left + i * tick_spacing)
        pygame.draw.rect(surface, (230, 181, 14), (tx, tick_y, 3, tick_height))

    # Draft meter
    draft_rect = pygame.Rect(
        18,
        SCREEN_HEIGHT - HUD_BLOCK_HEIGHT - LEFT_DRAFT_EXTRA - 10,
        LEFT_DRAFT_WIDTH,
        HUD_BLOCK_HEIGHT + LEFT_DRAFT_EXTRA,
    )
    pygame.draw.rect(surface, panel_color, draft_rect, border_radius=10)
    pygame.draw.rect(surface, border_color, draft_rect, 2, border_radius=10)
    meter = pygame.Rect(
        draft_rect.left + 10,
        draft_rect.top + 10,
        draft_rect.width - 20,
        draft_rect.height - 22,
    )
    fill_ratio = clamp(data.get("draft", 0.0), 0.0, 1.0)
    fill_height = meter.height * fill_ratio
    fill_points = [
        (meter.left, meter.bottom),
        (meter.right, meter.bottom),
        (meter.centerx, meter.bottom - fill_height),
    ]
    pygame.draw.polygon(surface, (39, 216, 90), fill_points)
    draft_label = font_small.render("Draft", True, (54, 255, 107))
    label_rot = pygame.transform.rotate(draft_label, 90)
    surface.blit(
        label_rot,
        (draft_rect.right + 4, draft_rect.centery - label_rot.get_height() // 2),
    )

    # Bottom HUD
    hud_width = min(720, SCREEN_WIDTH - 260)
    hud_rect = pygame.Rect(
        (SCREEN_WIDTH - hud_width) // 2,
        SCREEN_HEIGHT - HUD_BLOCK_HEIGHT - HUD_BOTTOM_MARGIN,
        hud_width,
        HUD_BLOCK_HEIGHT,
    )
    pygame.draw.rect(surface, hud_color, hud_rect, border_radius=12)
    pygame.draw.rect(surface, hud_border, hud_rect, 2, border_radius=12)

    spd_value = data.get("player_speed", 0.0)
    rpm_value = int(spd_value * 73)
    gear_value = min(6, max(1, int(spd_value / 45) + 1))
    temp_value = int(210 + max(0, spd_value - 160) * 1.1)
    speed_text = font.render(f"SPD {spd_value:06.2f}", True, track_text_color)
    temp_text = font_small.render(f"TEMP {temp_value}", True, (255, 255, 255))
    rpm_text = font.render(f"{rpm_value:05d} RPM", True, track_text_color)
    gear_text = font_small.render(f"GEAR {gear_value}", True, (255, 255, 255))

    left_x = hud_rect.left + 20
    surface.blit(speed_text, (left_x, hud_rect.top + 18))
    surface.blit(temp_text, (left_x, hud_rect.top + 54))
    right_x = hud_rect.right - rpm_text.get_width() - 20
    surface.blit(rpm_text, (right_x, hud_rect.top + 18))
    surface.blit(gear_text, (right_x, hud_rect.top + 54))

    diamond_size = 18
    diamond_surface = pygame.Surface((diamond_size, diamond_size), pygame.SRCALPHA)
    pygame.draw.rect(diamond_surface, (207, 42, 42), diamond_surface.get_rect(), border_radius=2)
    pygame.draw.rect(diamond_surface, (139, 28, 28), diamond_surface.get_rect(), 2, border_radius=2)
    rotated = pygame.transform.rotate(diamond_surface, 45)
    surface.blit(
        rotated,
        rotated.get_rect(center=(hud_rect.centerx, hud_rect.centery)).topleft,
    )

    # Lift button
    lift_width = 120
    lift_height = 52
    lift_rect = pygame.Rect(
        min(hud_rect.right + 16, SCREEN_WIDTH - lift_width - 12),
        hud_rect.bottom - lift_height - 12,
        lift_width,
        lift_height,
    )
    lift_color = (54, 234, 104) if not data.get("lift_active") else (104, 255, 145)
    pygame.draw.rect(surface, lift_color, lift_rect, border_radius=10)
    pygame.draw.rect(surface, (30, 164, 74), lift_rect, 3, border_radius=10)
    lift_text = font.render("Lift", True, (6, 43, 18))
    surface.blit(
        lift_text,
        (lift_rect.centerx - lift_text.get_width() // 2, lift_rect.centery - lift_text.get_height() // 2),
    )


def compute_turn_penalty(lap_progress):
    phase = lap_progress % 1.0
    return TURN_PENALTY_MAX * (math.sin(math.pi * phase * 2) ** 2)


class Car:
    def __init__(self, lane_index, distance, lane_positions, driver):
        self.lane_positions = lane_positions
        self.lane_index = lane_index
        self.distance = distance
        self.speed = 0.0
        self.driver = driver
        self.sprite = random.choice(driver.sprites)
        self.aggression = random.uniform(0.85, 1.2)
        self.size = pygame.Vector2(self.sprite.get_size())
        self.lane_change_timer = 0.0
        self.state = "RUNNING"      # RUNNING | CRASHING | DISABLED
        self.crash_timer = 0.0
        self.spin_angle = 0.0
        self.spin_speed = 0.0

    def update(self, delta, sim_player_speed, control_locked):
        self.lane_change_timer = max(0.0, self.lane_change_timer - delta)
        # Crash/disabled kinetics
        if self.state == "CRASHING":
            self.crash_timer -= delta
            self.spin_angle += self.spin_speed * delta
            target = sim_player_speed - 140.0
            accel = 420.0
            self.speed = move_toward(self.speed, target, accel * delta)
            self.distance -= (self.speed - sim_player_speed) * delta
            if self.crash_timer <= 0:
                self.state = "DISABLED"
            return self.distance < -400
        elif self.state == "DISABLED":
            self.speed = move_toward(self.speed, sim_player_speed - 220.0, 560.0 * delta)
            self.distance -= (self.speed - sim_player_speed) * delta
            return self.distance < -400
        if control_locked:
            target = sim_player_speed + (self.aggression - 1.0) * 12.0
            accel = 280.0
        else:
            target = sim_player_speed + (self.aggression - 1.0) * 32.0
            accel = 360.0 * self.aggression
        self.speed = move_toward(self.speed, target, accel * delta)
        self.distance -= (self.speed - sim_player_speed) * delta
        if control_locked:
            self.distance = max(self.distance, -48)
        return self.distance < -400

    def draw(self, surface, offset):
        center_y = self.lane_positions[self.lane_index]
        x = SCREEN_WIDTH / 2 - (self.distance - offset)
        base_rect = self.sprite.get_rect(center=(x, center_y))
        sprite_to_draw = self.sprite
        rect = base_rect
        if self.state in ("CRASHING", "DISABLED"):
            sprite_to_draw = pygame.transform.rotate(self.sprite, self.spin_angle)
            rect = sprite_to_draw.get_rect(center=base_rect.center)
        glow_rect = rect.inflate(28, 18)
        glow_surface = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            glow_surface,
            (*self.driver.accent, 70),
            glow_surface.get_rect(),
        )
        surface.blit(glow_surface, glow_rect.topleft)
        surface.blit(sprite_to_draw, rect)


def spawn_pack(lane_positions, preset, drivers):
    ai = []
    lane_count = max(1, preset.lane_count)
    base_distance = 120
    row_spacing = max(18.0, preset.row_gap * 0.5)
    field_target = preset.field_size if preset.field_size and preset.field_size > 1 else preset.pack_rows * lane_count
    ai_limit = max(3, field_target - 1 if preset.field_size else field_target)
    formation_lanes = [
        lane for lane in (preset.formation_lanes or list(range(lane_count))) if 0 <= lane < lane_count
    ]
    if not formation_lanes:
        formation_lanes = list(range(lane_count))
    columns = max(1, len(formation_lanes))
    ai_limit = min(ai_limit, preset.pack_rows * columns)
    driver_pool = drivers[:] or [create_default_driver()]
    random.shuffle(driver_pool)
    driver_sequence: list[DriverInfo] = []
    while len(driver_sequence) < ai_limit:
        driver_sequence.extend(driver_pool)
    driver_sequence = driver_sequence[:ai_limit]

    for idx, driver in enumerate(driver_sequence):
        row = idx // columns
        if row >= preset.pack_rows:
            break
        lane_index = formation_lanes[idx % columns]
        distance = base_distance + row * row_spacing
        jitter = random.uniform(-3, 3 * (row / max(1, preset.pack_rows)))
        ai.append(Car(lane_index, distance + jitter, lane_positions, driver))
    return ai


def build_two_wide_pack(
    lane_positions,
    preset,
    drivers,
    player_lane_index: int,
    player_row_index: int,
    row_spacing_override: float | None = None,
):
    """Create an ultra-tight two-wide grid and reserve the player's slot."""
    if preset.lane_count < 2 or not lane_positions:
        return []
    formation_lanes = [
        lane for lane in (preset.formation_lanes or list(range(preset.lane_count))) if 0 <= lane < preset.lane_count
    ]
    if len(formation_lanes) < 2:
        formation_lanes = list(range(min(2, preset.lane_count)))
    base_spacing = row_spacing_override if row_spacing_override is not None else preset.row_gap
    row_spacing = max(COLLISION_GAP + 1.0, 6.0, base_spacing)
    target_ai = (preset.field_size or (preset.pack_rows * len(formation_lanes))) - 1
    if target_ai <= 0:
        return []
    driver_pool = drivers[:] or [create_default_driver()]
    random.shuffle(driver_pool)
    driver_index = 0

    def take_driver():
        nonlocal driver_index
        driver = driver_pool[driver_index]
        driver_index = (driver_index + 1) % len(driver_pool)
        return driver

    base_distance = -player_row_index * row_spacing
    jitter_scale = row_spacing * QUICK_RACE_ROW_JITTER
    ai: list[Car] = []
    for row in range(preset.pack_rows):
        row_distance = base_distance + row * row_spacing
        for lane in formation_lanes[:2]:
            if row == player_row_index and lane == player_lane_index:
                continue
            car = Car(
                lane,
                row_distance + random.uniform(-jitter_scale, jitter_scale),
                lane_positions,
                take_driver(),
            )
            ai.append(car)
            if len(ai) >= target_ai:
                return ai
    return ai


def recycle_car(lane_positions, preset, drivers):
    lane_index = random.randrange(preset.lane_count)
    driver = random.choice(drivers)
    return Car(lane_index, random.uniform(520, 1500), lane_positions, driver)


def attempt_lane_changes(ai_cars, preset):
    for car in ai_cars:
        if car.lane_change_timer > 0:
            continue
        blocking = [other for other in ai_cars if other is not car and other.lane_index == car.lane_index]
        blocking = [other for other in blocking if 0 < other.distance - car.distance < 160]
        if not blocking:
            continue
        direction = random.choice([-1, 1])
        for delta_lane in (direction, -direction):
            new_lane = car.lane_index + delta_lane
            if not 0 <= new_lane < preset.lane_count:
                continue
            conflict = False
            for other in ai_cars:
                if other is car or other.lane_index != new_lane:
                    continue
                if abs(other.distance - car.distance) < 170:
                    conflict = True
                    break
            if conflict:
                continue
            car.lane_index = new_lane
            car.lane_change_timer = 0.6
            break


def gather_pack_stats(ai_cars, lane_count):
    stats = {
        "ahead": 0,
        "behind": 0,
        "closest_ahead": None,
        "lane_density": [0 for _ in range(lane_count)],
    }
    closest = 9999
    for car in ai_cars:
        if car.distance > 0:
            stats["ahead"] += 1
            closest = min(closest, car.distance)
        else:
            stats["behind"] += 1
        if 0 <= car.lane_index < lane_count and abs(car.distance) < 420:
            stats["lane_density"][car.lane_index] += 1
    if closest < 9999:
        stats["closest_ahead"] = closest
    return stats


def compute_draft_intensity(ai_cars, lane_index):
    min_gap = 999
    intensity = 0.0
    for car in ai_cars:
        if car.lane_index != lane_index:
            continue
        gap = car.distance
        if 0 < gap < 200:
            intensity = max(intensity, 1.0 - gap / 200)
            min_gap = min(min_gap, gap)
    return intensity, (min_gap if min_gap < 999 else None)


def apply_drafting(ai_cars, player_lane):
    lanes: dict[int, list[Car]] = defaultdict(list)
    for car in ai_cars:
        lanes[car.lane_index].append(car)
    player_contact = 0.0
    for lane_index, lane_cars in lanes.items():
        lane_cars.sort(key=lambda c: c.distance, reverse=True)
        for i in range(len(lane_cars) - 1):
            lead = lane_cars[i]
            trail = lane_cars[i + 1]
            gap = lead.distance - trail.distance
            if gap <= 0:
                continue
            if gap < 160:
                boost = 28.0 * (1 - gap / 160)
                trail.speed += boost
            if gap < 28:
                pressure = (28 - gap) / 28
                trail.speed += pressure * 32.0
                lead.speed += pressure * 18.0
                trail.distance = min(trail.distance, lead.distance - 14)
    for car in lanes.get(player_lane, []):
        gap = car.distance
        if 0 < gap < 42:
            contact = (42 - gap) / 42
            player_contact += contact * 30.0
            car.speed += contact * 28.0
    return min(player_contact, 50.0)


def is_lane_clear_for_player(target_lane: int, ai_cars, safety_distance: float = LANE_SAFETY_DISTANCE) -> bool:
    for car in ai_cars:
        if car.lane_index == target_lane and abs(car.distance) < safety_distance:
            return False
    return True


def resolve_collisions(ai_cars, player_lane_index: int, player_sim_speed: float) -> float:
    lanes = defaultdict(list)
    for c in ai_cars:
        lanes[c.lane_index].append(c)

    player_mph_delta = 0.0

    for lane, cars in lanes.items():
        cars.sort(key=lambda c: c.distance, reverse=True)
        for i in range(len(cars) - 1):
            ahead = cars[i]
            behind = cars[i + 1]
            if ahead.state != "RUNNING" or behind.state != "RUNNING":
                continue
            gap = ahead.distance - behind.distance
            if gap <= COLLISION_GAP:
                rel = behind.speed - ahead.speed
                if rel > CRASH_REL_UNITS:
                    for t in (ahead, behind):
                        t.state = "CRASHING"
                        t.crash_timer = 1.2
                        t.spin_speed = random.uniform(-220, 220)
                else:
                    transfer = max(0.0, rel * 0.45)
                    ahead.speed += transfer * 0.65
                    behind.speed = max(0.0, behind.speed - transfer * 0.35)
                behind.distance = min(behind.distance, ahead.distance - COLLISION_GAP)

    for car in lanes.get(player_lane_index, []):
        if car.state != "RUNNING":
            continue
        gap = car.distance
        if 0 < gap <= COLLISION_GAP:
            rel = player_sim_speed - car.speed
            if rel > CRASH_REL_UNITS:
                car.state = "CRASHING"
                car.crash_timer = 1.2
                car.spin_speed = random.uniform(-220, 220)
                player_mph_delta -= 8.0
            else:
                transfer = max(0.0, rel * 0.45)
                car.speed += transfer * 0.70
                player_mph_delta -= min(3.0, (transfer / SPEED_SCALE) * 0.35)
            car.distance = max(car.distance, COLLISION_GAP)
    return player_mph_delta


def build_pack_view(ai_cars, limit=4):
    ahead = sorted([car for car in ai_cars if car.distance > 0], key=lambda c: c.distance)[:limit]
    behind = sorted([car for car in ai_cars if car.distance <= 0], key=lambda c: c.distance, reverse=True)[:limit]
    return ahead, behind


def draw_track_banner(surface, preset, lap, laps_total, font_large, font_small, lap_progress):
    banner_rect = pygame.Rect(32, 18, 420, 92)
    banner_surface = pygame.Surface(banner_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(banner_surface, (18, 22, 32, HUD_ALPHA), banner_surface.get_rect(), border_radius=20)
    name_text = font_large.render(preset.name, True, (235, 240, 255))
    tagline_text = font_small.render(preset.tagline, True, (170, 195, 230))
    laps_text = font_small.render(f"Lap {lap}/{laps_total}", True, (200, 220, 250))
    banner_surface.blit(name_text, (24, 10))
    banner_surface.blit(tagline_text, (24, 48))
    banner_surface.blit(laps_text, (banner_surface.get_width() - laps_text.get_width() - 24, 12))
    progress_rect = pygame.Rect(24, banner_surface.get_height() - 24, banner_surface.get_width() - 48, 8)
    pygame.draw.rect(banner_surface, (35, 45, 70), progress_rect, border_radius=6)
    fill_width = int(progress_rect.width * clamp(lap_progress, 0.0, 1.0))
    if fill_width > 0:
        pygame.draw.rect(
            banner_surface,
            (120, 210, 255),
            pygame.Rect(progress_rect.x, progress_rect.y, fill_width, progress_rect.height),
            border_radius=6,
        )
    surface.blit(banner_surface, banner_rect.topleft)


def draw_lane_meter(surface, rect, lane_count, density, player_lane):
    gap = 8
    lane_width = (rect.width - gap * (lane_count - 1)) / lane_count if lane_count else rect.width
    for lane in range(lane_count):
        lane_rect = pygame.Rect(rect.x + lane * (lane_width + gap), rect.y, lane_width, rect.height)
        fill_ratio = min(1.0, density[lane] / 4) if density else 0
        base_color = (50, 60, 80)
        pygame.draw.rect(surface, base_color, lane_rect, border_radius=6)
        if fill_ratio > 0:
            fill_rect = lane_rect.copy()
            fill_rect.height = int(lane_rect.height * fill_ratio)
            fill_rect.y = lane_rect.bottom - fill_rect.height
            pygame.draw.rect(surface, (110, 210, 240), fill_rect, border_radius=6)
        border_color = (200, 240, 255) if lane == player_lane else (120, 140, 170)
        pygame.draw.rect(surface, border_color, lane_rect, width=2, border_radius=6)


def draw_driver_card(
    surface,
    font_large,
    font_small,
    font_digit,
    driver,
    player_speed,
    draft_intensity,
    draft_gap,
    pack_stats,
    lane_count,
    player_lane,
):
    card_rect = pygame.Rect(32, SCREEN_HEIGHT - 220, 520, 188)
    card_surface = pygame.Surface(card_rect.size, pygame.SRCALPHA)
    accent = driver.accent
    pygame.draw.rect(
        card_surface,
        (*accent, HUD_ALPHA),
        card_surface.get_rect(),
        border_radius=26,
    )
    content_rect = card_surface.get_rect().inflate(-32, -32)
    speed_text = font_digit.render(f"{int(player_speed):03d}", True, (250, 255, 255))
    mph_text = font_small.render("MPH", True, (230, 240, 255))
    card_surface.blit(speed_text, (content_rect.x, content_rect.y))
    card_surface.blit(mph_text, (content_rect.x + speed_text.get_width() + 12, content_rect.y + 12))
    name_text = font_large.render(f"#{driver.car_num} {driver.driver_name}", True, (10, 15, 25))
    detail_text = font_small.render(f"{driver.team} • {driver.manufacturer}", True, (10, 18, 30))
    role_desc = ROLE_FLAVOR.get(driver.role, driver.role)
    role_text = font_small.render(f"{driver.role} • {role_desc}", True, (10, 18, 30))
    rarity_text = font_small.render(f"Rarity {driver.rarity}★", True, (10, 18, 30))
    card_surface.blit(name_text, (content_rect.x, content_rect.y + 70))
    card_surface.blit(detail_text, (content_rect.x, content_rect.y + 110))
    card_surface.blit(role_text, (content_rect.x, content_rect.y + 140))
    card_surface.blit(rarity_text, (content_rect.x + 310, content_rect.y + 140))
    meter_rect = pygame.Rect(content_rect.right - 220, content_rect.y, 200, 20)
    pygame.draw.rect(card_surface, (20, 28, 40), meter_rect, border_radius=12)
    inner_width = int((meter_rect.width - 6) * clamp(draft_intensity, 0.0, 1.0))
    if inner_width > 0:
        pygame.draw.rect(
            card_surface,
            (110, 220, 255),
            pygame.Rect(meter_rect.x + 3, meter_rect.y + 3, inner_width, meter_rect.height - 6),
            border_radius=9,
        )
    draft_label = font_small.render(f"Draft {int(draft_intensity * 100):02d}%", True, (10, 18, 30))
    gap_value = "--" if draft_gap is None else f"{int(draft_gap)}m"
    gap_label = font_small.render(f"Gap {gap_value}", True, (10, 18, 30))
    card_surface.blit(draft_label, (meter_rect.x, meter_rect.bottom + 8))
    card_surface.blit(gap_label, (meter_rect.x + 110, meter_rect.bottom + 8))
    lane_rect = pygame.Rect(content_rect.x + 250, content_rect.y + 60, 220, 50)
    draw_lane_meter(card_surface, lane_rect, lane_count, pack_stats.get("lane_density"), player_lane)
    surface.blit(card_surface, card_rect.topleft)


def draw_pack_sidebar(surface, font_small, font_large, ahead, behind):
    panel_rect = pygame.Rect(SCREEN_WIDTH - 260, 110, 220, 440)
    panel_surface = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel_surface, (15, 18, 28, HUD_ALPHA), panel_surface.get_rect(), border_radius=26)
    title = font_large.render("Pack", True, (235, 240, 255))
    panel_surface.blit(title, (20, 16))
    y = 70
    for label, segment in (("Ahead", ahead), ("Behind", behind)):
        segment_title = font_small.render(label, True, (170, 190, 220))
        panel_surface.blit(segment_title, (20, y))
        y += 24
        if not segment:
            empty = font_small.render("--", True, (90, 110, 140))
            panel_surface.blit(empty, (22, y))
            y += 32
            continue
        for car in segment:
            text = font_small.render(f"#{car.driver.car_num} {car.driver.driver_name}", True, car.driver.accent)
            gap = font_small.render(f"{abs(int(car.distance))}m", True, (200, 220, 250))
            panel_surface.blit(text, (24, y))
            panel_surface.blit(gap, (panel_surface.get_width() - gap.get_width() - 20, y))
            y += 28
        y += 8
    surface.blit(panel_surface, panel_rect.topleft)


def draw_menu(screen, fonts, presets, selected_track, drivers, driver_index):
    font, font_large, font_small = fonts
    screen.fill((6, 10, 18))
    title = font_large.render("DraftMaster Inspired Pack Racing", True, (235, 240, 255))
    screen.blit(title, (SCREEN_WIDTH / 2 - title.get_width() / 2, 40))
    instruction = font_small.render("↑/↓ Track • ←/→ Driver • Enter Race", True, (180, 195, 220))
    screen.blit(instruction, (SCREEN_WIDTH / 2 - instruction.get_width() / 2, 80))
    left_rect = pygame.Rect(100, 150, 420, 420)
    pygame.draw.rect(screen, (14, 18, 28), left_rect, border_radius=20)
    for i, preset in enumerate(presets):
        color = (110, 150, 200)
        if i == selected_track:
            color = (120, 220, 255)
        label = font.render(f"{preset.name}", True, color)
        tag = font_small.render(preset.tagline, True, (140, 160, 190))
        screen.blit(label, (left_rect.x + 24, left_rect.y + 30 + i * 110))
        screen.blit(tag, (left_rect.x + 24, left_rect.y + 66 + i * 110))
    if not drivers:
        return
    driver = drivers[driver_index]
    right_rect = pygame.Rect(SCREEN_WIDTH - 520, 150, 360, 420)
    pygame.draw.rect(screen, (14, 18, 28), right_rect, border_radius=20)
    driver_title = font.render(f"#{driver.car_num} {driver.driver_name}", True, driver.accent)
    team_text = font_small.render(f"{driver.team} • {driver.manufacturer}", True, (200, 220, 240))
    screen.blit(driver_title, (right_rect.x + 24, right_rect.y + 24))
    screen.blit(team_text, (right_rect.x + 24, right_rect.y + 64))
    sprite = driver.sprites[0]
    sprite_rect = sprite.get_rect(center=(right_rect.centerx, right_rect.y + 200))
    screen.blit(sprite, sprite_rect)
    rarity = font_small.render(f"Role {driver.role} • {driver.rarity}★", True, (200, 220, 240))
    screen.blit(rarity, (right_rect.x + 24, right_rect.bottom - 60))


def draw_title_menu(screen, fonts, hover_index: int | None):
    font, font_large, font_small = fonts
    screen.fill((6, 10, 18))
    title = font_large.render("Drafting Pack Racer", True, (235, 240, 255))
    subtitle = font_small.render("DM2-inspired quick race", True, (180, 195, 220))
    screen.blit(title, (SCREEN_WIDTH / 2 - title.get_width() / 2, 80))
    screen.blit(subtitle, (SCREEN_WIDTH / 2 - subtitle.get_width() / 2, 120))

    cx = SCREEN_WIDTH // 2
    start_y = 220
    rects = []
    for i, label in enumerate(TITLE_BUTTONS):
        r = pygame.Rect(0, 0, BUTTON_W, BUTTON_H)
        r.center = (cx, start_y + i * (BUTTON_H + BUTTON_GAP))
        rects.append(r)
        color = (18, 22, 32)
        border = (120, 180, 255) if hover_index == i else (70, 90, 130)
        pygame.draw.rect(screen, color, r, border_radius=12)
        pygame.draw.rect(screen, border, r, width=2, border_radius=12)
        txt = font.render(label, True, (230, 240, 255))
        screen.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))

    return rects


def pick_default_driver_index(drivers):
    if not drivers:
        return 0
    best_idx = 0
    best_score = -1
    for idx, driver in enumerate(drivers):
        score = driver.rarity * 10 + (5 if driver.role == "Dominator" else 0)
        if score > best_score:
            best_idx = idx
            best_score = score
    return best_idx


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 36)
    font_large = pygame.font.Font(None, 48)
    font_small = pygame.font.Font(None, 28)
    font_digit = pygame.font.Font(None, 82)

    driver_library = load_cup21_drivers()
    if not driver_library:
        driver_library = [create_default_driver()]
    selected_driver_index = pick_default_driver_index(driver_library)

    state = "TITLE"
    selected_track = 0
    active_preset = TRACK_PRESETS[selected_track]
    lane_positions = build_lane_positions(active_preset.lane_count, active_preset.lane_width, active_preset.lane_spacing)
    track_bounds = compute_track_bounds(lane_positions, active_preset.lane_width, active_preset.lane_spacing)
    ribbons = build_speed_ribbons(track_bounds)
    ai_cars = []
    rolling_timer = 0.0
    control_locked = False

    player_driver = driver_library[selected_driver_index]
    player_sprite = random.choice(player_driver.sprites)
    player_lane_target = active_preset.lane_count // 2
    player_lane_value = float(player_lane_target)
    lane_cooldown = 0.0
    player_speed_mph = 0.0
    draft_bonus = 0.0
    contact_boost_cache = 0.0
    lap_distance = 4200.0
    total_distance = 0.0
    current_lap = 1
    main_hover = None
    green_flash_timer = 0.0
    leaders_collapsed = False
    pause_active = False
    lift_active = False

    def start_quick_race(selected_track_index: int | None = None, selected_driver_index_local: int | None = None):
        nonlocal active_preset, lane_positions, track_bounds, ribbons, ai_cars
        nonlocal player_driver, player_sprite, player_lane_target, player_lane_value
        nonlocal lane_cooldown, player_speed_mph, draft_bonus, lap_distance, total_distance, current_lap
        nonlocal rolling_timer, state, selected_track, selected_driver_index, contact_boost_cache
        nonlocal main_hover, green_flash_timer
        nonlocal leaders_collapsed, pause_active, lift_active

        if selected_track_index is None:
            selected_track_index = 0
            for idx, preset in enumerate(TRACK_PRESETS):
                if preset.name == DEFAULT_QUICK_RACE_PRESET:
                    selected_track_index = idx
                    break

        selected_track = selected_track_index
        preset_base = TRACK_PRESETS[selected_track]
        quick_race_layout = preset_base.name == DEFAULT_QUICK_RACE_PRESET
        if quick_race_layout:
            active_preset = replace(
                preset_base,
                lane_count=2,
                lane_spacing=QUICK_RACE_LANE_SPACING,
                lane_width=QUICK_RACE_LANE_WIDTH,
                pack_rows=QUICK_RACE_PACK_ROWS,
                row_gap=QUICK_RACE_ROW_GAP,
                tagline="Two-wide 43-car pace pack, bumpers touching.",
                formation_lanes=[0, 1],
                field_size=DEFAULT_FIELD_SIZE,
            )
        else:
            active_preset = preset_base

        lane_positions = build_lane_positions(active_preset.lane_count, active_preset.lane_width, active_preset.lane_spacing)
        track_bounds = compute_track_bounds(lane_positions, active_preset.lane_width, active_preset.lane_spacing)
        ribbons = build_speed_ribbons(track_bounds)
        player_lane_target = active_preset.lane_count // 2
        player_row_index = active_preset.pack_rows - 1
        if quick_race_layout:
            player_lane_target = clamp(QUICK_RACE_PLAYER_LANE, 0, active_preset.lane_count - 1)
            player_row_index = clamp(QUICK_RACE_PLAYER_ROW, 0, active_preset.pack_rows - 1)
            ai_cars = build_two_wide_pack(
                lane_positions,
                active_preset,
                driver_library,
                player_lane_target,
                player_row_index,
                row_spacing_override=active_preset.row_gap,
            )
            if not ai_cars:
                ai_cars = spawn_pack(lane_positions, active_preset, driver_library)
        else:
            ai_cars = spawn_pack(lane_positions, active_preset, driver_library)
        driver_index_to_use = selected_driver_index_local if selected_driver_index_local is not None else selected_driver_index
        driver_index_to_use = max(0, min(driver_index_to_use, len(driver_library) - 1))
        selected_driver_index = driver_index_to_use
        player_driver = driver_library[driver_index_to_use]
        player_sprite = random.choice(player_driver.sprites)
        player_lane_value = float(player_lane_target)
        lane_cooldown = 0.0
        player_speed_mph = 0.0
        draft_bonus = 0.0
        contact_boost_cache = 0.0
        lap_distance = 4200.0
        total_distance = 0.0
        current_lap = 1
        rolling_timer = ROLLING_DURATION
        main_hover = None
        green_flash_timer = 0.0
        leaders_collapsed = False
        pause_active = False
        lift_active = False
        state = "RACE"

    running = True
    while running:
        delta = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE:
                    lift_active = False
                continue
            if state == "TITLE":
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        start_quick_race()
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                elif event.type == pygame.MOUSEMOTION:
                    main_hover = None
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pass
                continue
            elif state == "MENU" and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DOWN:
                    selected_track = (selected_track + 1) % len(TRACK_PRESETS)
                elif event.key == pygame.K_UP:
                    selected_track = (selected_track - 1) % len(TRACK_PRESETS)
                elif event.key == pygame.K_RIGHT:
                    selected_driver_index = (selected_driver_index + 1) % len(driver_library)
                elif event.key == pygame.K_LEFT:
                    selected_driver_index = (selected_driver_index - 1) % len(driver_library)
                elif event.key == pygame.K_RETURN:
                    start_quick_race(selected_track, selected_driver_index)
                elif event.key == pygame.K_ESCAPE:
                    running = False
            elif state == "RACE" and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    state = "MENU"
                    lift_active = False
                elif event.key == pygame.K_TAB:
                    leaders_collapsed = not leaders_collapsed
                elif event.key == pygame.K_p:
                    pause_active = not pause_active
                elif event.key == pygame.K_SPACE:
                    lift_active = True

        if state == "TITLE":
            rects = draw_title_menu(screen, (font, font_large, font_small), main_hover)
            mx, my = pygame.mouse.get_pos()
            main_hover = None
            for i, rect in enumerate(rects):
                if rect.collidepoint(mx, my):
                    main_hover = i
                    break
            if pygame.mouse.get_pressed(num_buttons=3)[0]:
                if main_hover == 0:
                    start_quick_race()
                elif main_hover == 1:
                    main_hover = None
                    state = "MENU"
                elif main_hover == 2:
                    running = False
            pygame.display.flip()
            continue

        if state == "MENU":
            draw_menu(screen, (font, font_large, font_small), TRACK_PRESETS, selected_track, driver_library, selected_driver_index)
            pygame.display.flip()
            continue

        rolling_timer = max(0.0, rolling_timer - delta)
        control_locked = rolling_timer > 0.0
        just_unlocked = False
        if not control_locked and green_flash_timer <= 0.0:
            if rolling_timer == 0.0:
                green_flash_timer = GREEN_FLASH_TIME
                just_unlocked = True
        green_flash_timer = max(0.0, green_flash_timer - delta)

        keys = pygame.key.get_pressed()
        lane_cooldown = max(0.0, lane_cooldown - delta)
        if control_locked:
            player_lane_target = active_preset.lane_count // 2
        else:
            if lane_cooldown <= 0.0:
                if keys[pygame.K_LEFT]:
                    desired = max(0, player_lane_target - 1)
                    if desired != player_lane_target and is_lane_clear_for_player(desired, ai_cars, LANE_SAFETY_DISTANCE):
                        player_lane_target = desired
                        lane_cooldown = LANE_CHANGE_COOLDOWN
                elif keys[pygame.K_RIGHT]:
                    desired = min(active_preset.lane_count - 1, player_lane_target + 1)
                    if desired != player_lane_target and is_lane_clear_for_player(desired, ai_cars, LANE_SAFETY_DISTANCE):
                        player_lane_target = desired
                        lane_cooldown = LANE_CHANGE_COOLDOWN
        player_lane_value = move_toward(player_lane_value, player_lane_target, delta * 6.5)
        player_lane_index = int(round(clamp(player_lane_value, 0, active_preset.lane_count - 1)))
        player_center_y = lane_center_at(lane_positions, player_lane_value)

        prev_lap_progress = (total_distance / lap_distance) if lap_distance else 0.0
        turn_penalty = 0.0 if control_locked else compute_turn_penalty(prev_lap_progress)

        brake = keys[pygame.K_DOWN] if not control_locked else False
        if control_locked:
            progress = clamp(1.0 - rolling_timer / ROLLING_DURATION, 0.0, 1.0)
            target_mph = ROLLING_START_MIN_MPH + progress * (ROLLING_START_MAX_MPH - ROLLING_START_MIN_MPH)
        else:
            target_mph = CONTROLLED_BASE_MPH + draft_bonus * 18.0 + contact_boost_cache * 0.28 - turn_penalty
            if brake:
                target_mph = BRAKE_MPH
            target_mph = clamp(target_mph, BRAKE_MPH, CONTROLLED_BASE_MPH + 40.0)
        player_speed_mph = move_toward(player_speed_mph, target_mph, 120.0 * delta)
        sim_speed = player_speed_mph * SPEED_SCALE
        total_distance += sim_speed * delta
        if total_distance >= lap_distance:
            total_distance -= lap_distance
            current_lap = min(current_lap + 1, active_preset.laps)
        lap_progress = total_distance / lap_distance

        for car in ai_cars[:]:
            if car.update(delta, sim_speed, control_locked):
                ai_cars.remove(car)
                ai_cars.append(recycle_car(lane_positions, active_preset, driver_library))
        if not control_locked:
            attempt_lane_changes(ai_cars, active_preset)
        contact_boost = apply_drafting(ai_cars, player_lane_index)
        contact_boost_cache = contact_boost
        mph_delta = 0.0
        if not control_locked:
            mph_delta = resolve_collisions(ai_cars, player_lane_index, sim_speed)
        if mph_delta != 0.0:
            player_speed_mph = max(0.0, player_speed_mph + mph_delta)

        for ribbon in ribbons:
            ribbon.update(delta, sim_speed)

        scroll = total_distance
        track_rect = draw_track(
            screen,
            lane_positions,
            active_preset.lane_width,
            active_preset.lane_spacing,
            active_preset.lane_count,
            scroll,
            ribbons,
        )
        for car in ai_cars:
            car.draw(screen, total_distance)
        player_rect = player_sprite.get_rect(center=(SCREEN_WIDTH // 2, int(player_center_y)))
        glow = pygame.Surface(player_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*player_driver.accent, 80), glow.get_rect())
        screen.blit(glow, player_rect.topleft)
        screen.blit(player_sprite, player_rect)

        pack_stats = gather_pack_stats(ai_cars, active_preset.lane_count)
        ahead, behind = build_pack_view(ai_cars)
        draft_intensity, draft_gap = compute_draft_intensity(ai_cars, player_lane_index)
        draft_bonus = draft_intensity
        leader_entries = build_leader_entries(ai_cars, sim_speed, limit=6)

        draw_pack_sidebar(screen, font_small, font_large, ahead, behind)
        draw_driver_card(
            screen,
            font,
            font_small,
            font_digit,
            player_driver,
            player_speed_mph,
            draft_intensity,
            draft_gap,
            pack_stats,
            active_preset.lane_count,
            player_lane_index,
        )

        ui_payload = {
            "track_name": active_preset.name,
            "lap": current_lap,
            "laps_total": active_preset.laps,
            "leaders": leader_entries,
            "control_locked": control_locked,
            "draft": draft_intensity,
            "lift_active": lift_active,
            "pause_active": pause_active,
            "leaders_collapsed": leaders_collapsed,
            "brake": brake,
            "player_speed": player_speed_mph,
        }
        draw_dm2_ui(screen, (font, font_large, font_small), ui_payload)

        if current_lap >= active_preset.laps and lap_progress >= 0.95:
            finish = font_large.render("Race Complete", True, (255, 220, 120))
            screen.blit(
                finish,
                (SCREEN_WIDTH / 2 - finish.get_width() / 2, SCREEN_HEIGHT / 2 - finish.get_height() / 2),
            )

        if green_flash_timer > 0.0:
            banner = font_large.render("GREEN!", True, (120, 255, 140))
            screen.blit(
                banner,
                (
                    SCREEN_WIDTH / 2 - banner.get_width() / 2,
                    TOP_BAR_HEIGHT + 6,
                ),
            )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
