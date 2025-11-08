extends Node

var selected_index: int = 0
var selected_preset: Dictionary = null

var track_presets := [
	{
		"name": "3-Lane Oval",
		"lane_count": 3,
		"lane_width": 210.0,
		"lane_spacing": 220.0,
		"pack_rows": 6,
		"row_gap": 70.0,
		"laps": 10,
		"tagline": "Wide middle lane, tight draft funnels."
	},
	{
		"name": "Superspeedway 5",
		"lane_count": 5,
		"lane_width": 200.0,
		"lane_spacing": 200.0,
		"pack_rows": 8,
		"row_gap": 60.0,
		"laps": 8,
		"tagline": "Packed, relentless pace with extra lanes."
	},
	{
		"name": "Drafting Tri-Oval",
		"lane_count": 4,
		"lane_width": 205.0,
		"lane_spacing": 210.0,
		"pack_rows": 5,
		"row_gap": 78.0,
		"laps": 6,
		"tagline": "Triangular drafting that rewards timing."
	}
]

func _ready() -> void:
	set_selected_preset(selected_index)

func set_selected_preset(index: int) -> Dictionary:
	selected_index = clamp(index, 0, track_presets.size() - 1)
	selected_preset = track_presets[selected_index]
	return selected_preset

func get_active_preset() -> Dictionary:
	if selected_preset == null:
		set_selected_preset(selected_index)
	return selected_preset

func apply_active_preset(car_manager: Node, track: Node, race_controller: Node) -> void:
	var preset = get_active_preset()
	if car_manager and car_manager.has_method("apply_track_preset"):
		car_manager.apply_track_preset(preset)
	if track:
		track.lane_count = preset["lane_count"]
		if track.has_method("set_lane_width"):
			track.set_lane_width(preset["lane_width"])
		else:
			track.lane_width = preset["lane_width"]
	if race_controller:
		race_controller.total_laps = preset["laps"]
