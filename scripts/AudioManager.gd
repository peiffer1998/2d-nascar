extends Node

const ENGINE_STREAM := preload("res://assets/audio/engine_hum.wav")
const DRAFT_STREAM := preload("res://assets/audio/draft_sizzle.wav")
const START_STREAM := preload("res://assets/audio/start_chime.wav")
const FINISH_STREAM := preload("res://assets/audio/finish_chime.wav")
const CLICK_STREAM := preload("res://assets/audio/ui_click.wav")

@onready var engine_player: AudioStreamPlayer = $EngineLoop
@onready var draft_player: AudioStreamPlayer = $DraftPulse
@onready var start_player: AudioStreamPlayer = $StartChime
@onready var finish_player: AudioStreamPlayer = $FinishChime
@onready var click_player: AudioStreamPlayer = $Click

func _ready() -> void:
	engine_player.stream = ENGINE_STREAM
	engine_player.volume_db = -10
	engine_player.bus = "Master"
	engine_player.loop = true
	engine_player.play()
	draft_player.stream = DRAFT_STREAM
	draft_player.bus = "Master"
	start_player.stream = START_STREAM
	finish_player.stream = FINISH_STREAM
	click_player.stream = CLICK_STREAM

func set_engine_intensity(frac: float) -> void:
	var intensity = clamp(frac, 0.0, 1.0)
	engine_player.pitch_scale = lerp(0.85, 1.3, intensity)
	engine_player.volume_db = lerp(-14, -2, intensity)

func trigger_draft() -> void:
	if not draft_player.playing:
		draft_player.play()

func play_start() -> void:
	start_player.play()

func play_finish() -> void:
	finish_player.play()

func play_click() -> void:
	click_player.play()
