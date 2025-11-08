extends VBoxContainer

@export var car_manager_path: NodePath
@export var max_nearby_display: int = 6
@export var highlight_color: Color = Color(0.9, 0.65, 0.1)
@export var normal_color: Color = Color(0.55, 0.85, 0.95)

var car_manager: Node
var lane_labels: Array = []

func _ready() -> void:
	if car_manager_path and car_manager_path != NodePath(""):
		car_manager = get_node(car_manager_path)
	set_process(true)

func _process(delta: float) -> void:
	_refresh_labels()

func _refresh_labels() -> void:
	if car_manager == null or not car_manager.has_method("get_lane_load"):
		return
	var lane_data = car_manager.get_lane_load()
	_ensure_labels(lane_data.size())
	for i in range(lane_data.size()):
		var info = lane_data[i]
		var label = lane_labels[i]
		var nearby = info["nearby"]
		var ahead = info["ahead"]
		var behind = info["behind"]
		var draft_percent = int(clamp(info["draft"] * 100.0, 0, 999))
		label.text = "Lane %d | near %d | ahead %d | behind %d | draft %d%%" % [i + 1, nearby, ahead, behind, draft_percent]
		var intensity = clamp(float(nearby) / max(max_nearby_display, 1), 0.0, 1.0)
		var color = normal_color.linear_interpolate(highlight_color, intensity)
		label.add_color_override("font_color", color)

func _ensure_labels(count: int) -> void:
	while lane_labels.size() < count:
		var label = Label.new()
		label.horizontal_alignment = Label.HORIZONTAL_ALIGNMENT_LEFT
		label.custom_minimum_size = Vector2(380, 0)
		add_child(label)
		lane_labels.append(label)
	while lane_labels.size() > count:
		var label = lane_labels.pop_back()
		remove_child(label)
		label.queue_free()
