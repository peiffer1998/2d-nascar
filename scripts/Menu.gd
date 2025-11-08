extends Control

@onready var track_select = $MenuPanel/TrackSelect
@onready var info_label = $MenuPanel/TrackInfo
@onready var start_button = $MenuPanel/StartButton
@onready var quit_button = $MenuPanel/QuitButton
@onready var audio_player = $UIAudio

func _ready() -> void:
	_populate_tracks()
	track_select.connect("item_selected", Callable(self, "_on_track_selected"))
	start_button.pressed.connect(Callable(self, "_start_race"))
	quit_button.pressed.connect(Callable(self, "_quit_game"))
	audio_player.stream = preload("res://assets/audio/ui_click.wav")
	_update_info()

func _populate_tracks() -> void:
	track_select.clear()
	for preset in GameSettings.track_presets:
		track_select.add_item(preset["name"])
	_track_select_update_selection()

func _on_track_selected(index: int) -> void:
	GameSettings.set_selected_preset(index)
	_update_info()
	_play_click()

func _track_select_update_selection() -> void:
	var selected_index = GameSettings.selected_index
	if selected_index >= 0 and selected_index < track_select.get_item_count():
		track_select.selected = selected_index

func _update_info() -> void:
	var preset = GameSettings.get_active_preset()
	info_label.text = "%d Lanes • Pack rows %d • %d laps\n%s" % [preset["lane_count"], preset["pack_rows"], preset["laps"], preset["tagline"]]

func _start_race() -> void:
	_play_click()
	get_tree().change_scene_to_file("res://scenes/Race.tscn")

func _quit_game() -> void:
	_play_click()
	get_tree().quit()

func _play_click() -> void:
	if audio_player and audio_player.stream:
		audio_player.play()
