extends Node2D
class_name Car

enum CarState { RUNNING, CRASHING, DISABLED }

@export var base_color: Color = Color(1, 0.25, 0.25)
@export var is_player: bool = false

# Velocity & power model (game units; tuned for ~190-200 mph at max)
@export var min_speed: float = 280.0
@export var max_speed: float = 560.0
@export var engine_accel: float = 520.0      # forward accel at full throttle
@export var braking: float = 580.0
@export var base_drag: float = 0.00085       # v^2 coefficient in game units
@export var draft_drag_factor: float = 0.55  # fraction of drag removed at full draft
@export var side_draft_factor: float = 0.08  # additional drag when being side drafted

# Draft & size
@export var draft_boost: float = 120.0
@export var length: float = 90.0
@export var width: float = 46.0

# Laneing
@export var lane_positions: Array = []
@export var lane_index: int = 1
@export var lane_smooth_speed: float = 8.0

# Visuals
@export var sprite_texture: Texture2D setget set_sprite_texture
@export var sprite_scale: Vector2 = Vector2(1, 1) setget set_sprite_scale

# Runtime
var speed: float = 0.0
var desired_speed: float = 0.0
var distance_ahead: float = 0.0
var race_active: bool = false
var draft_effect_intensity: float = 0.0
var side_draft_penalty: float = 0.0
var state: CarState = CarState.RUNNING
var crash_timer: float = 0.0
var throttle: float = 1.0
var brake_input: float = 0.0

var _is_ready: bool = false
var _sprite_texture: Texture2D
var _sprite_scale: Vector2 = Vector2(1, 1)

@onready var sprite_node: Sprite2D = $Sprite
@onready var collider: Area2D = $Collider if has_node("Collider") else null

func _ready():
	if lane_positions.size() > 0:
		lane_index = clamp(lane_index, 0, lane_positions.size() - 1)
		position.x = lane_positions[lane_index].x
	set_sprite_texture(sprite_texture)
	set_sprite_scale(sprite_scale)
	_is_ready = true

func _process(delta: float) -> void:
	if lane_positions.size() == 0:
		return
	_update_lane_position(delta)
	_update_controls()
	_apply_speed_model(delta)
	_update_crash_state(delta)
	_update_visuals()

func _update_controls() -> void:
	if is_player:
		# Full throttle unless braking; supports holding Up in the future if desired.
		brake_input = Input.is_action_pressed("ui_down") ? 1.0 : 0.0
		throttle = 1.0 - clamp(brake_input, 0.0, 1.0)
	else:
		# AI provides throttle implicitly via target speed; keep full throttle here.
		throttle = 1.0
		brake_input = 0.0

func _apply_speed_model(delta: float) -> void:
	if state != CarState.RUNNING:
		return
	if not race_active:
		_coast_to_grid(delta)
		return

	# Drag with v^2, reduced by draft, increased by side-draft penalty
	var side_penalty = side_draft_penalty * side_draft_factor
	var drag_scale = 1.0 - draft_effect_intensity * draft_drag_factor + side_penalty
	drag_scale = clamp(drag_scale, 0.35, 1.25)
	var drag_force = base_drag * speed * speed * drag_scale

	var accel = engine_accel * throttle
	var brake_force = braking * brake_input
	var net = accel - drag_force - brake_force

	# Limit: can exceed max_speed slightly under strong draft/bump
	var allowed_max = max_speed + draft_boost * 0.3
	speed = clamp(speed + net * delta, min_speed, allowed_max)

func _update_crash_state(delta: float) -> void:
	if state == CarState.CRASHING:
		crash_timer -= delta
		# Sharper slow; disable draft stuff while crashing
		var slow = braking * 1.8 * delta
		speed = max(0.0, speed - slow)
		draft_effect_intensity = 0.0
		side_draft_penalty = 0.0
		if crash_timer <= 0.0:
			state = CarState.DISABLED
	elif state == CarState.DISABLED:
		speed = max(0.0, speed - braking * delta)

func impact_bump(transfer: float) -> void:
	# Small forward push, used for bump drafting
	speed = min(speed + transfer, max_speed + draft_boost * 0.5)

func impact_slow(amount: float) -> void:
	speed = max(0.0, speed - amount)

func crash(force: float = 1.0) -> void:
	if state != CarState.RUNNING:
		return
	state = CarState.CRASHING
	crash_timer = clamp(0.8 + force * 0.01, 0.8, 1.6)

func apply_ai_speed(target_speed: float, delta: float, aggression: float = 1.0) -> void:
	if state != CarState.RUNNING:
		return
	desired_speed = clamp(target_speed, min_speed, max_speed)
	var accel_rate = engine_accel * aggression
	speed = _move_toward(speed, desired_speed, accel_rate * delta)

func apply_draft_bonus(delta: float, intensity: float) -> void:
	if state != CarState.RUNNING:
		return
	draft_effect_intensity = clamp(intensity, 0.0, 1.0)

func hold_speed(target_speed: float, delta: float) -> void:
	if state != CarState.RUNNING:
		return
	speed = _move_toward(speed, target_speed, (engine_accel + braking) * 0.5 * delta)

func set_lane_positions(positions: Array) -> void:
	lane_positions = positions
	if lane_positions.size() == 0:
		return
	lane_index = clamp(lane_index, 0, lane_positions.size() - 1)
	if not _is_ready:
		position.x = lane_positions[lane_index].x

func set_lane_index(value: int) -> void:
	lane_index = clamp(value, 0, lane_positions.size() - 1)

func shift_lane(offset: int) -> void:
	set_lane_index(lane_index + offset)

func set_distance(distance: float) -> void:
	distance_ahead = distance
	if not is_player:
		position.y = -distance_ahead

func set_race_active(active: bool) -> void:
	race_active = active
	if not race_active:
		desired_speed = min_speed * 0.4
		speed = _move_toward(speed, desired_speed, braking * 0.5)

func _coast_to_grid(delta: float) -> void:
	var grid_speed = min_speed * 0.35
	speed = _move_toward(speed, grid_speed, braking * delta)

func get_speed_fraction() -> float:
	return clamp(speed / max_speed, 0.0, 1.0)

func _update_lane_position(delta: float) -> void:
	var target_x = lane_positions[lane_index].x
	position.x = lerp(position.x, target_x, lane_smooth_speed * delta)

func _update_visuals() -> void:
	update()

func _draw() -> void:
	if sprite_node and sprite_node.visible:
		return
	var size = Vector2(46, 90)
	var car_rect = Rect2(-size.x / 2, -size.y / 2, size.x, size.y)
	var tint = base_color.linear_interpolate(Color(1, 1, 1), get_speed_fraction() * 0.6)
	draw_rect(car_rect, tint, true, 0.0)
	draw_rect(car_rect, Color(0.07, 0.07, 0.07), false, 3.0)
	var headlight = Rect2(-size.x / 2 + 8, -size.y / 2 + 6, size.x - 16, 8)
	draw_rect(headlight, Color(1, 0.95, 0.6, 0.65))
	var tail_light = Rect2(-size.x / 2 + 6, size.y / 2 - 18, size.x - 12, 10)
	draw_rect(tail_light, Color(1, 0.2, 0.2))

func set_sprite_texture(value: Texture2D) -> void:
	_sprite_texture = value
	if sprite_node:
		sprite_node.texture = value
		sprite_node.visible = value != null

func set_sprite_scale(value: Vector2) -> void:
	_sprite_scale = value
	if sprite_node:
		sprite_node.scale = value

func _move_toward(value: float, target: float, step: float) -> float:
	if value < target:
		return min(value + step, target)
	elif value > target:
		return max(value - step, target)
	return target
