extends Node2D
class_name Car

@export var base_color: Color = Color(1, 0.25, 0.25)
@export var is_player: bool = false
@export var min_speed: float = 280.0
@export var max_speed: float = 560.0
@export var acceleration: float = 460.0
@export var braking: float = 580.0
@export var draft_boost: float = 120.0
@export var lane_positions: Array = []
@export var lane_index: int = 1
@export var lane_smooth_speed: float = 8.0
@export var sprite_texture: Texture2D setget set_sprite_texture
@export var sprite_scale: Vector2 = Vector2(1, 1) setget set_sprite_scale

var speed: float = 0.0
var desired_speed: float = 0.0
var distance_ahead: float = 0.0
var _is_ready: bool = false
var race_active: bool = false
var draft_effect_intensity: float = 0.0
var _sprite_texture: Texture2D
var _sprite_scale: Vector2 = Vector2(1, 1)

@onready var sprite_node: Sprite2D = $Sprite

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
	if is_player:
		_apply_player_speed(delta)
	_update_visuals()

func _update_lane_position(delta: float) -> void:
	var target_x = lane_positions[lane_index].x
	position.x = lerp(position.x, target_x, lane_smooth_speed * delta)

func _apply_player_speed(delta: float) -> void:
	if not race_active:
		_coast_to_grid(delta)
		return

	var brake = Input.is_action_pressed("ui_down")
	desired_speed = max_speed
	if brake:
		desired_speed = min(min_speed + 60, desired_speed)
	speed = _move_toward(speed, desired_speed, (acceleration + braking) * 0.5 * delta)

func apply_ai_speed(target_speed: float, delta: float, aggression: float = 1.0) -> void:
	desired_speed = clamp(target_speed, min_speed, max_speed)
	var accel_rate = acceleration * aggression
	speed = _move_toward(speed, desired_speed, accel_rate * delta)

func apply_draft_bonus(delta: float, intensity: float) -> void:
	var bonus = draft_boost * intensity
	speed = min(max_speed + bonus * 0.3, speed + bonus * delta)

func hold_speed(target_speed: float, delta: float) -> void:
	speed = _move_toward(speed, target_speed, (acceleration + braking) * 0.5 * delta)

func set_lane_positions(positions: Array) -> void:
	lane_positions = positions
	if lane_positions.size() == 0:
		return
	lane_index = clamp(lane_index, 0, lane_positions.size() - 1)
	if not _is_ready:
		position.x = lane_positions[lane_index].x

func set_lane_index(index: int) -> void:
	lane_index = clamp(index, 0, lane_positions.size() - 1)
	update()

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

func set_sprite_texture(value: Texture2D) -> void:
	_sprite_texture = value
	if sprite_node:
		sprite_node.texture = value
		sprite_node.visible = value != null

func set_sprite_scale(value: Vector2) -> void:
	_sprite_scale = value
	if sprite_node:
		sprite_node.scale = value

func get_speed_fraction() -> float:
	return clamp(speed / max_speed, 0.0, 1.0)

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

func _move_toward(value: float, target: float, step: float) -> float:
	if value < target:
		return min(value + step, target)
	elif value > target:
		return max(value - step, target)
	return target
