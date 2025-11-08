extends Node2D

@export var lane_count: int = 3
@export var lane_width: float = 210.0
@export var stripe_spacing: float = 90.0
@export var stripe_length: float = 34.0
@export var stripe_color: Color = Color(1, 1, 1, 0.35)
@export var track_color: Color = Color(0.08, 0.095, 0.14)
@export var lane_line_color: Color = Color(1, 1, 1, 0.35)
@export var lane_line_width: float = 5.0
@export var shoulder_color: Color = Color(0.04, 0.04, 0.08, 0.85)

var scroll_offset: float = 0.0

func advance(speed: float, delta: float) -> void:
	scroll_offset += speed * delta
	scroll_offset = fposmod(scroll_offset, stripe_spacing)
	update()

func _draw() -> void:
	var viewport_size = get_viewport_rect().size
	var half_height = viewport_size.y / 2
	var total_track_width = lane_width * lane_count
	var left = -total_track_width / 2
	var track_rect = Rect2(left, -half_height, total_track_width, viewport_size.y)
	draw_rect(track_rect, track_color)
	draw_rect(Rect2(left - lane_width * 0.2, -half_height, lane_width * 0.2, viewport_size.y), shoulder_color)
	draw_rect(Rect2(left + total_track_width, -half_height, lane_width * 0.2, viewport_size.y), shoulder_color)
	for i in range(lane_count + 1):
		var x = left + i * lane_width
		draw_line(Vector2(x, -half_height), Vector2(x, half_height), lane_line_color, lane_line_width)
	var midpoints = []
	for lane_index in range(lane_count):
		midpoints.append(left + lane_width * lane_index + lane_width / 2)
	var steps = int((viewport_size.y + stripe_spacing * 2) / stripe_spacing) + 2
	var base_y = -half_height - stripe_spacing
	for i in range(steps):
		var y_pos = base_y + i * stripe_spacing + scroll_offset
	for x in midpoints:
		var rect = Rect2(x - 9, y_pos, 18, stripe_length)
		draw_rect(rect, stripe_color)

func set_lane_width(value: float) -> void:
	lane_width = value
	update()
