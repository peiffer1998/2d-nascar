import json
import math
import os
import random
import re
from collections import defaultdict
from dataclasses import dataclass

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


def draw_track(surface, lane_positions, lane_height, lane_spacing, lane_count, scroll, ribbons):
    surface.fill((4, 6, 12))
    gradient = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    for y in range(SCREEN_HEIGHT):
        ratio = y / SCREEN_HEIGHT
        shade = int(14 + ratio * 28)
        pygame.draw.line(gradient, (shade, shade, shade + 12, 85), (0, y), (SCREEN_WIDTH, y))
    surface.blit(gradient, (0, 0))
    if not lane_positions:
        return pygame.Rect(0, 0, 0, 0)
    track_top, track_bottom = compute_track_bounds(lane_positions, lane_height, lane_spacing)
    track_rect = pygame.Rect(0, track_top, SCREEN_WIDTH, track_bottom - track_top)
    asphalt = pygame.Surface((SCREEN_WIDTH, track_rect.height), pygame.SRCALPHA)
    for y in range(0, track_rect.height, 4):
        ratio = y / max(1, track_rect.height)
        base = int(20 + ratio * 32)
        pygame.draw.rect(asphalt, (base, base, base + 14), (0, y, SCREEN_WIDTH, 4))
    surface.blit(asphalt, (0, track_top))
    apron = track_rect.inflate(-22, -18)
    if apron.width > 0 and apron.height > 0:
        pygame.draw.rect(surface, (28, 34, 52), apron, width=6, border_radius=34)
    pygame.draw.rect(surface, (10, 12, 18), (0, track_top - 40, SCREEN_WIDTH, 40))
    pygame.draw.rect(surface, (10, 12, 18), (0, track_bottom, SCREEN_WIDTH, 40))
    pygame.draw.rect(surface, (18, 20, 26), track_rect, border_radius=38)
    inner_track = track_rect.inflate(-64, -64)
    pygame.draw.rect(surface, (26, 30, 40), inner_track, border_radius=38)
    grass_rect = inner_track.inflate(-36, -36)
    if grass_rect.width > 0 and grass_rect.height > 0:
        pygame.draw.rect(surface, (18, 92, 52), grass_rect, border_radius=32)
        stripe_gap = 44
        for offset in range(0, grass_rect.width, stripe_gap):
            stripe_rect = pygame.Rect(grass_rect.left + offset, grass_rect.top, min(24, grass_rect.width - offset), grass_rect.height)
            color = (16, 70, 36) if ((offset // stripe_gap) % 2 == 0) else (24, 110, 60)
            pygame.draw.rect(surface, color, stripe_rect)
    center_line_width = 4
    lane_gap = lane_height + lane_spacing
    base_y = lane_positions[0] - lane_height / 2
    dash_length = 20
    dash_gap = 24
    for i in range(lane_count + 1):
        y = int(base_y + i * lane_gap)
        for x in range(-dash_length, SCREEN_WIDTH + dash_length, dash_length + dash_gap):
            pygame.draw.line(surface, (180, 210, 240, 160), (x, y), (min(SCREEN_WIDTH, x + dash_length), y), center_line_width)
    start_line_x = SCREEN_WIDTH // 2 + START_LINE_OFFSET
    for y in range(track_top + 32, track_bottom - 32, 26):
        rect = pygame.Rect(start_line_x, y, 12, 18)
        pygame.draw.rect(surface, (255, 255, 255, 220), rect)
    stand_top = track_top - 62
    stand_bottom = track_bottom + 18
    stand_width = 48
    stand_gap = 12
    for base_x in range(10, SCREEN_WIDTH - stand_width, stand_width + stand_gap):
        stand_rect = pygame.Rect(base_x, stand_top, stand_width, 48)
        pygame.draw.rect(surface, (16, 30, 58), stand_rect, border_radius=10)
        pygame.draw.rect(
            surface,
            (34, 66, 120),
            stand_rect.inflate(-16, -10),
            border_radius=6,
        )
        stand_rect = pygame.Rect(base_x, stand_bottom, stand_width, 40)
        pygame.draw.rect(surface, (16, 30, 58), stand_rect, border_radius=10)
        pygame.draw.rect(
            surface,
            (50, 90, 150),
            stand_rect.inflate(-14, -8),
            border_radius=5,
        )
    for ribbon in ribbons:
        ribbon.draw(surface)
    stripe_spacing = 200
    stripe_width = 22
    stripe_height = track_rect.height
    offset = (scroll * 0.4) % stripe_spacing
    for i in range(-4, SCREEN_WIDTH // stripe_spacing + 8):
        x = int(i * stripe_spacing + offset)
        stripe_rect = pygame.Rect(x, track_top, stripe_width, stripe_height)
        pygame.draw.rect(surface, (38, 58, 92), stripe_rect)
    return track_rect


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

    def update(self, delta, sim_player_speed, control_locked):
        self.lane_change_timer = max(0.0, self.lane_change_timer - delta)
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
        rect = self.sprite.get_rect(center=(x, center_y))
        glow_rect = rect.inflate(28, 18)
        glow_surface = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            glow_surface,
            (*self.driver.accent, 70),
            glow_surface.get_rect(),
        )
        surface.blit(glow_surface, glow_rect.topleft)
        surface.blit(self.sprite, rect)


def spawn_pack(lane_positions, preset, drivers):
    ai = []
    lane_count = max(1, preset.lane_count)
    base_distance = 120
    row_spacing = max(36, preset.row_gap * 0.85)
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
        jitter = random.uniform(-6, 6 * (row / max(1, preset.pack_rows)))
        ai.append(Car(lane_index, distance + jitter, lane_positions, driver))
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

    state = "MENU"
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

    running = True
    while running:
        delta = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
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
                    active_preset = TRACK_PRESETS[selected_track]
                    lane_positions = build_lane_positions(
                        active_preset.lane_count, active_preset.lane_width, active_preset.lane_spacing
                    )
                    track_bounds = compute_track_bounds(
                        lane_positions, active_preset.lane_width, active_preset.lane_spacing
                    )
                    ribbons = build_speed_ribbons(track_bounds)
                    ai_cars = spawn_pack(lane_positions, active_preset, driver_library)
                    player_driver = driver_library[selected_driver_index]
                    player_sprite = random.choice(player_driver.sprites)
                    player_lane_target = active_preset.lane_count // 2
                    player_lane_value = float(player_lane_target)
                    lane_cooldown = 0.0
                    player_speed_mph = 0.0
                    draft_bonus = 0.0
                    lap_distance = 4200.0
                    total_distance = 0.0
                    current_lap = 1
                    rolling_timer = ROLLING_DURATION
                    state = "RACE"
                elif event.key == pygame.K_ESCAPE:
                    running = False
            elif state == "RACE" and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    state = "MENU"

        if state == "MENU":
            draw_menu(screen, (font, font_large, font_small), TRACK_PRESETS, selected_track, driver_library, selected_driver_index)
            pygame.display.flip()
            continue

        rolling_timer = max(0.0, rolling_timer - delta)
        control_locked = rolling_timer > 0.0

        keys = pygame.key.get_pressed()
        lane_cooldown = max(0.0, lane_cooldown - delta)
        if control_locked:
            player_lane_target = active_preset.lane_count // 2
        else:
            if lane_cooldown <= 0.0:
                if keys[pygame.K_LEFT] and player_lane_target > 0:
                    player_lane_target -= 1
                    lane_cooldown = LANE_CHANGE_COOLDOWN
                elif keys[pygame.K_RIGHT] and player_lane_target < active_preset.lane_count - 1:
                    player_lane_target += 1
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
        if control_locked and track_rect.height:
            rolling_label = font_small.render("Rolling start — controls locked", True, (255, 230, 200))
            countdown_label = font_small.render(f"{rolling_timer:.1f}s", True, (255, 140, 60))
            screen.blit(rolling_label, (SCREEN_WIDTH / 2 - rolling_label.get_width() / 2, track_rect.top - 44))
            screen.blit(countdown_label, (SCREEN_WIDTH / 2 - countdown_label.get_width() / 2, track_rect.top - 18))
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

        draw_track_banner(screen, active_preset, current_lap, active_preset.laps, font_large, font_small, lap_progress)
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

        if current_lap >= active_preset.laps and lap_progress >= 0.95:
            finish = font_large.render("Race Complete", True, (255, 220, 120))
            screen.blit(
                finish,
                (SCREEN_WIDTH / 2 - finish.get_width() / 2, SCREEN_HEIGHT / 2 - finish.get_height() / 2),
            )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
