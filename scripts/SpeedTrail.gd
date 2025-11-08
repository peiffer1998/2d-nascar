extends Particles2D

@export var min_speed_frac: float = 0.2
@export var max_speed_frac: float = 1.0
@export var min_emission: int = 6
@export var max_emission: int = 32
@export var draft_boost_emission: int = 14
@export var min_velocity: float = 42.0
@export var max_velocity: float = 130.0
@export var trail_length: float = 0.65

var parent_car: Car
var material: ParticlesMaterial

func _ready() -> void:
	parent_car = get_parent() as Car
	material = ParticlesMaterial.new()
	material.lifetime = trail_length
	material.direction = Vector3(0, 1, 0)
	material.angle = 18
	material.angle_random = 0.65
	material.gravity = Vector3(0, -640, 0)
	material.initial_velocity = min_velocity
	material.initial_velocity_random = 0.4
	material.scale = 0.45
	material.scale_random = 0.45
	var ramp = Gradient.new()
	ramp.add_point(0.0, Color(0.98, 0.95, 1.0, 0.7))
	ramp.add_point(1.0, Color(0.5, 0.6, 1.0, 0.05))
	material.color_ramp = ramp
	material.emission_shape = ParticlesMaterial.EMISSION_SHAPE_POINT
	process_material = material
	texture = _build_texture()
	emitting = false
	set_process(true)

func _process(delta: float) -> void:
	if not parent_car or not parent_car.is_player:
		emitting = false
		return
	emitting = parent_car.race_active and parent_car.speed > parent_car.min_speed * 0.2
	var speed_frac := clamp(parent_car.speed / parent_car.max_speed, 0.0, 1.0)
	var normalized := 0.0
	if max_speed_frac > min_speed_frac:
		normalized = clamp((speed_frac - min_speed_frac) / (max_speed_frac - min_speed_frac), 0.0, 1.0)
	var base_emission := lerp(min_emission, max_emission, normalized)
	emission_amount = int(base_emission + draft_boost_emission * parent_car.draft_effect_intensity)
	material.initial_velocity = lerp(min_velocity, max_velocity, normalized + parent_car.draft_effect_intensity * 0.35)
	material.scale = lerp(0.35, 0.7, normalized + parent_car.draft_effect_intensity * 0.4)

func _build_texture() -> Texture2D:
	var image = Image.new()
	var size = 8
	image.create(size, size, false, Image.FORMAT_RGBA8)
	image.lock()
	for x in range(size):
		for y in range(size):
			var dist = Vector2(x - size / 2.0 + 0.25, y - size / 2.0 + 0.25).length()
			var alpha = clamp(1.2 - dist * 0.65, 0.0, 1.0)
			image.set_pixel(x, y, Color(1, 1, 1, alpha))
	image.unlock()
	var tex = ImageTexture.create_from_image(image)
	tex.flags = Texture.FLAG_FILTER
	return tex
