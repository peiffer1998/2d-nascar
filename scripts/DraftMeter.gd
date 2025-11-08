extends Control

@export var car_manager_path: NodePath
@export var meter_height: float = 18.0
@export var gauge_color: Color = Color(0.25, 0.75, 1.0, 0.9)
@export var background_color: Color = Color(0.03, 0.03, 0.06, 0.8)
@export var fade_speed: float = 5.0

var car_manager: Node
var label: Label
var intensity: float = 0.0
var target_intensity: float = 0.0
var gap_text: String = "--"

func _ready() -> void:
	car_manager = get_node_or_null(car_manager_path)
	label = Label.new()
	label.horizontal_alignment = Label.HORIZONTAL_ALIGNMENT_LEFT
	label.vertical_alignment = Label.VERTICAL_ALIGNMENT_TOP
	label.position = Vector2(0, meter_height + 6)
	add_child(label)
	set_process(true)

func _process(delta: float) -> void:
	if car_manager == null or not car_manager.has_method("get_player_draft_stats"):
		return
	var stats = car_manager.get_player_draft_stats()
	target_intensity = clamp(stats["draft"], 0.0, 1.0)
	intensity = lerp(intensity, target_intensity, delta * fade_speed)
	var gap_value = stats["gap"]
	gap_text = gap_value < car_manager.pack_snapshot_range ? "%dm" % int(gap_value) : "--"
	label.text = "Draft boost %d%% | gap %s" % [int(round(intensity * 100.0)), gap_text]
	update()

func _draw() -> void:
	var width = rect_size.x
	if width <= 0:
		return
	var bg_rect = Rect2(0, 0, width, meter_height)
	draw_rect(bg_rect, background_color)
	var fill_width = width * intensity
	if fill_width > 0:
		draw_rect(Rect2(0, 0, fill_width, meter_height), gauge_color)
