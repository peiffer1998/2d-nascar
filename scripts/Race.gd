extends Node2D

var lane_switch_cooldown: float = 0.18
var lane_timer: float = 0.0

@onready var track = $Track
@onready var car_manager = $CarManager
@onready var player = $PlayerCar
@onready var speed_label = $HUD/TopPanel/SpeedLabel
@onready var info_label = $HUD/TopPanel/InfoLabel
@onready var track_label = $HUD/TopPanel/TrackLabel
@onready var restart_button = $HUD/TopPanel/RestartButton
@onready var menu_button = $HUD/TopPanel/MenuButton
@onready var position_label = $HUD/TopPanel/PositionLabel
@onready var race_controller = $RaceController
@onready var audio_manager = $AudioManager
var units_to_mph := 0.35

func _ready() -> void:
	lane_timer = 0.0
	set_process(true)
	randomize()
	GameSettings.apply_active_preset(null, track, race_controller)
	var preset = GameSettings.get_active_preset()
	if track_label:
		track_label.text = "Track: %s" % preset["name"]
	if restart_button:
		restart_button.connect("pressed", Callable(self, "_on_restart_pressed"))
	if menu_button:
		menu_button.connect("pressed", Callable(self, "_on_menu_pressed"))
	if car_manager and car_manager.has_variable("units_to_mph"):
		units_to_mph = car_manager.units_to_mph

func _process(delta: float) -> void:
	track.advance(player.speed, delta)
	_handle_lane_input(delta)
	_update_hud()

func _handle_lane_input(delta: float) -> void:
	lane_timer = max(0.0, lane_timer - delta)
	if lane_timer > 0:
		return
	if Input.is_action_just_pressed("ui_left"):
		_request_player_lane(-1)
		lane_timer = lane_switch_cooldown
	elif Input.is_action_just_pressed("ui_right"):
		_request_player_lane(1)
		lane_timer = lane_switch_cooldown

func _request_player_lane(offset: int) -> void:
	var next = clamp(player.lane_index + offset, 0, player.lane_positions.size() - 1)
	if car_manager and car_manager.is_lane_clear_for_player(next, 120.0):
		player.shift_lane(offset)
	else:
		# blocked; tiny feedback hook (optional sfx in AudioManager)
		pass

func _update_hud() -> void:
	var mph = int(round(player.speed * units_to_mph))
	speed_label.text = "SPEED: %03d MPH" % mph
	var stats = car_manager.get_pack_snapshot()
	var draft_percent = int(clamp(stats["draft_avg"] * 100.0, 0, 999))
	var gap = stats["closest_gap"]
	var gap_display = gap < car_manager.pack_snapshot_range ? "%d" % int(gap) : "--"
	info_label.text = "Use ←/→ to switch lanes, ↑/↓ to control throttle.\nPack ahead %d | behind %d | lane mates %d | draft %d%% | gap %s" % [stats["ahead"], stats["behind"], stats["lane_mates"], draft_percent, gap_display]
	if position_label:
		var position = stats["ahead"] + 1
		position_label.text = "POSITION: %d" % position

func _on_restart_pressed() -> void:
	if audio_manager and audio_manager.has_method("play_click"):
		audio_manager.play_click()
	get_tree().reload_current_scene()

func _on_menu_pressed() -> void:
	if audio_manager and audio_manager.has_method("play_click"):
		audio_manager.play_click()
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
