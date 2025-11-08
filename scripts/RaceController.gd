extends Node

enum RaceState { COUNTDOWN, RACING, FINISHED }

@export var car_manager_path: NodePath
@export var player_car_path: NodePath
@export var label_path: NodePath
@export var lap_label_path: NodePath
@export var audio_manager_path: NodePath
@export var countdown_duration: float = 3.2
@export var lap_distance: float = 4200.0
@export var total_laps: int = 10

var car_manager: Node
var player_car: Car
var status_label: Label
var lap_label: Label
var audio_manager: Node
var state: int = RaceState.COUNTDOWN
var countdown_timer: float = 0.0
var race_timer: float = 0.0
var current_lap: int = 1
var lap_accum: float = 0.0
var draft_cooldown: float = 0.0

func _ready() -> void:
	car_manager = get_node_or_null(car_manager_path)
	player_car = get_node_or_null(player_car_path) as Car
	status_label = get_node_or_null(label_path) as Label
	lap_label = get_node_or_null(lap_label_path) as Label
	audio_manager = get_node_or_null(audio_manager_path)
	countdown_timer = countdown_duration
	race_timer = 0.0
	state = RaceState.COUNTDOWN
	current_lap = 1
	lap_accum = 0.0
	if player_car:
		player_car.set_race_active(false)
	set_process(true)

func _process(delta: float) -> void:
	match state:
		RaceState.COUNTDOWN:
			countdown_timer = max(countdown_timer - delta, 0.0)
			if countdown_timer == 0.0:
				_start_race()
		RaceState.RACING:
			race_timer += delta
			_update_lap_progress(delta)
		_:
			pass
	_update_label()
	_update_audio(delta)
	if draft_cooldown > 0:
		draft_cooldown = max(draft_cooldown - delta, 0.0)

func _start_race() -> void:
	state = RaceState.RACING
	current_lap = 1
	lap_accum = 0.0
	if player_car:
		player_car.set_race_active(true)
	if audio_manager and audio_manager.has_method("play_start"):
		audio_manager.play_start()

func _finish_race() -> void:
	if state == RaceState.FINISHED:
		return
	state = RaceState.FINISHED
	if player_car:
		player_car.set_race_active(false)
	if audio_manager and audio_manager.has_method("play_finish"):
		audio_manager.play_finish()

func _update_lap_progress(delta: float) -> void:
	if not player_car or state != RaceState.RACING:
		return
	lap_accum += player_car.speed * delta
	while lap_accum >= lap_distance and state == RaceState.RACING:
		lap_accum -= lap_distance
		current_lap += 1
		if current_lap > total_laps:
			current_lap = total_laps
			_finish_race()
			return

func _update_label() -> void:
	if status_label:
		status_label.text = get_status_text()
	if lap_label:
		lap_label.text = get_lap_label_text()

func get_status_text() -> String:
	match state:
		RaceState.COUNTDOWN:
			return "START IN %.1f" % countdown_timer
		RaceState.RACING:
			var minutes = int(race_timer / 60)
			var seconds = race_timer % 60
			return "RACE %02d:%05.2f" % [minutes, seconds]
		RaceState.FINISHED:
			return "RACE FINISHED"
	return "WAIT"

func get_lap_label_text() -> String:
	if total_laps <= 0:
		return "Lap tracking disabled"
	var display = "Lap %d/%d" % [min(current_lap, total_laps), total_laps]
	if state == RaceState.FINISHED:
		display += " (Complete)"
	return display

func get_lap_fraction() -> float:
	if lap_distance <= 0:
		return 0.0
	return clamp(lap_accum / lap_distance, 0.0, 1.0)

func _update_audio(delta: float) -> void:
	if not audio_manager or not player_car:
		return
	var speed_frac = clamp(player_car.speed / player_car.max_speed, 0.0, 1.0)
	if audio_manager.has_method("set_engine_intensity"):
		audio_manager.set_engine_intensity(speed_frac)
	var draft_stats = car_manager.get_player_draft_stats() if car_manager else null
	if draft_stats:
		var intensity = draft_stats["draft"]
		if intensity > 0.3 and draft_cooldown <= 0.0 and audio_manager.has_method("trigger_draft"):
			audio_manager.trigger_draft()
			draft_cooldown = 0.4

func is_racing() -> bool:
	return state == RaceState.RACING

func is_finished() -> bool:
	return state == RaceState.FINISHED
