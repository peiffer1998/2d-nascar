extends CanvasLayer

@export var player_path: NodePath
@export var aura_thickness: float = 80.0
@export var aura_color: Color = Color(1, 0.92, 0.7)
@export var base_alpha: float = 0.05
@export var max_alpha: float = 0.55
@export var fade_speed: float = 6.0

var player_car: Car
var intensity: float = 0.0
var edges := {}

func _ready() -> void:
	player_car = get_node_or_null(player_path) as Car
	if not player_car:
		return
	edges["top"] = _make_rect(Vector2(0, aura_thickness), Control.ANCHOR_PRESET_TOP_WIDE)
	edges["bottom"] = _make_rect(Vector2(0, aura_thickness), Control.ANCHOR_PRESET_BOTTOM_WIDE)
	edges["left"] = _make_rect(Vector2(aura_thickness, 0), Control.ANCHOR_PRESET_LEFT_WIDE)
	edges["right"] = _make_rect(Vector2(aura_thickness, 0), Control.ANCHOR_PRESET_RIGHT_WIDE)

func _make_rect(size: Vector2, preset: int) -> ColorRect:
	var node = ColorRect.new()
	node.color = aura_color
	node.rect_min_size = size
	node.anchors_preset = preset
	add_child(node)
	return node

func _process(delta: float) -> void:
	if player_car == null:
		return
	var target = clamp(player_car.speed / player_car.max_speed, 0.0, 1.0)
	intensity = lerp(intensity, target, delta * fade_speed)
	var alpha = base_alpha + (max_alpha - base_alpha) * intensity
	for rect in edges.values():
		rect.modulate.a = alpha
