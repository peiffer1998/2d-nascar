extends Node2D

const PLAYER_CAR_SPRITE := preload("res://assets/car_blue.png")
const AI_CAR_SPRITES := [
	preload("res://assets/car_blue.png"),
	preload("res://assets/car_yellow.png"),
	preload("res://assets/car_red.png"),
	preload("res://assets/car_gray.png")
]
const PLAYER_SPRITE_SCALE := Vector2(0.92, 0.92)
const AI_SPRITE_SCALE := Vector2(0.78, 0.78)

@export var car_scene: PackedScene
@export var player_node: NodePath
@export var lane_count: int = 3
@export var lane_spacing: float = 220.0
@export var pack_rows: int = 6
@export var row_gap: float = 70.0
@export var ai_depth_range: Vector2 = Vector2(500, 1400)
@export var draft_distance: float = 170.0
@export var pack_snapshot_range: float = 480.0
@export var race_controller_path: NodePath
@export var lane_change_interval: float = 1.5
@export var lane_change_threshold: float = 58.0
@export var car_length: float = 90.0
@export var collision_gap: float = 72.0
@export var crash_rel_speed_threshold: float = 90.0   # units/s closing rate to trigger crash
@export var side_draft_range: float = 95.0
@export var side_draft_strength: float = 0.08
@export var units_to_mph: float = 0.35                # used by HUD via Race.gd

var player_car: Car
var lane_positions: Array = []
var ai_cars: Array = []
var lane_zones = [[0, 1], [0, 1], [2, 1], [0, 2], [1, 0], [2, 1]]
var player_draft_intensity: float = 0.0
var player_closest_gap: float = 0.0
var race_controller: Node

func _ready():
	randomize()
	GameSettings.apply_active_preset(self, null, null)
	player_car = get_node(player_node)
	race_controller = get_node_or_null(race_controller_path)
	player_draft_intensity = 0.0
	player_closest_gap = draft_distance
	_build_lane_positions()
	player_car.set_lane_positions(lane_positions)
	player_car.set_lane_index(clamp(int(lane_count / 2), 0, lane_positions.size() - 1))
	if PLAYER_CAR_SPRITE:
		player_car.sprite_texture = PLAYER_CAR_SPRITE
		player_car.sprite_scale = PLAYER_SPRITE_SCALE
		player_car.base_color = Color(0.3, 0.55, 0.92)
	_spawn_initial_pack()

func _process(delta: float) -> void:
	if not _is_racing():
		_hold_grid(delta)
		return
	var player_speed = player_car.speed
	for car_data in ai_cars:
		var ai = car_data["car"] as Car
		var target_speed = player_speed + (car_data["aggression"] - 1.0) * 40.0
		ai.apply_ai_speed(target_speed, delta, car_data["aggression"])
		car_data["distance"] -= (ai.speed - player_speed) * delta
		car_data["lane"] = ai.lane_index
		ai.set_lane_index(car_data["lane"])
		ai.set_distance(car_data["distance"])
		if car_data["distance"] < -120.0:
			_respawn_car(car_data)

	_update_ai_lane_changes(delta)
	_apply_pack_drafting(delta)
	_apply_side_drafting(delta)
	_detect_and_resolve_collisions(delta)
	_update_player_draft()

func get_lane_load() -> Array:
	var lanes = []
	for lane_index in range(lane_count):
		lanes.append({
			"nearby": 0,
			"ahead": 0,
			"behind": 0,
			"draft": 0.0
		})
	for car_data in ai_cars:
		var lane_index = car_data["lane"]
		if lane_index < 0 or lane_index >= lane_count:
			continue
		var distance = car_data["distance"]
		if abs(distance) > pack_snapshot_range:
			continue
		var lane_stats = lanes[lane_index]
		lane_stats["nearby"] += 1
		lane_stats["draft"] += car_data["draft_intensity"]
		if distance > 10.0:
			lane_stats["ahead"] += 1
		elif distance < -10.0:
			lane_stats["behind"] += 1
	for lane_stats in lanes:
		if lane_stats["nearby"] > 0:
			lane_stats["draft"] = lane_stats["draft"] / lane_stats["nearby"]
		else:
			lane_stats["draft"] = 0.0
	return lanes

func get_pack_snapshot() -> Dictionary:
	var player_lane = player_car.lane_index
	var stats = {
		"nearby": 0,
		"ahead": 0,
		"behind": 0,
		"lane_mates": 0,
		"draft_avg": 0.0,
		"closest_gap": pack_snapshot_range
	}
	var lane_load = get_lane_load()
	for lane_index in range(lane_load.size()):
		var lane_stats = lane_load[lane_index]
		stats["nearby"] += lane_stats["nearby"]
		stats["ahead"] += lane_stats["ahead"]
		stats["behind"] += lane_stats["behind"]
		if lane_index == player_lane:
			stats["lane_mates"] = lane_stats["nearby"]
		stats["draft_avg"] += lane_stats["draft"] * lane_stats["nearby"]
	for car_data in ai_cars:
		var dist = car_data["distance"]
		if dist > 0 and abs(dist) <= pack_snapshot_range:
			stats["closest_gap"] = min(stats["closest_gap"], dist)
	if stats["nearby"] > 0:
		stats["draft_avg"] = stats["draft_avg"] / stats["nearby"]
	else:
		stats["draft_avg"] = 0.0
	return stats

func _build_lane_positions() -> void:
	lane_positions.clear()
	var total_width = lane_spacing * (lane_count - 1)
	var start_x = -total_width / 2
	for i in range(lane_count):
		lane_positions.append(Vector2(start_x + i * lane_spacing, 0))

func _spawn_initial_pack() -> void:
	var start_distance = 220.0
	for row_index in range(pack_rows):
		var lanes = lane_zones[row_index % lane_zones.size()]
		var base_distance = start_distance + row_index * row_gap
		for lane_index in lanes:
			_spawn_ai_in_lane(lane_index, base_distance + (lane_index * 18))

func _spawn_ai_in_lane(lane_index: int, distance: float) -> void:
	if car_scene == null:
		return
	var ai_car = car_scene.instantiate() as Car
	add_child(ai_car)
	ai_car.is_player = false
	ai_car.base_color = Color(0.8 - lane_index * 0.12, 0.3 + lane_index * 0.2, 0.3)
	ai_car.set_lane_positions(lane_positions)
	ai_car.set_lane_index(lane_index)
	ai_car.set_distance(distance)
	var sprite_choice = AI_CAR_SPRITES[randi() % AI_CAR_SPRITES.size()]
	ai_car.sprite_texture = sprite_choice
	ai_car.sprite_scale = AI_SPRITE_SCALE
	var entry = {
		"car": ai_car,
		"lane": lane_index,
		"distance": distance,
		"aggression": 0.9 + randf() * 0.4,
		"draft_intensity": 0.0,
		"lane_change_timer": 0.0
	}
	ai_cars.append(entry)

func apply_track_preset(preset: Dictionary) -> void:
	if preset.has("lane_count"):
		lane_count = preset["lane_count"]
	if preset.has("lane_spacing"):
		lane_spacing = preset["lane_spacing"]
	if preset.has("pack_rows"):
		pack_rows = preset["pack_rows"]
	if preset.has("row_gap"):
		row_gap = preset["row_gap"]

func _respawn_car(car_data) -> void:
	car_data["distance"] = randf_range(ai_depth_range.x, ai_depth_range.y)
	car_data["lane"] = randi() % lane_count
	car_data["aggression"] = 0.85 + randf() * 0.5
	car_data["draft_intensity"] = 0.0
	var ai = car_data["car"] as Car
	ai.set_lane_index(car_data["lane"])
	ai.set_distance(car_data["distance"])

func _apply_pack_drafting(delta: float) -> void:
	for current in ai_cars:
		var closest_gap = draft_distance
		var intensity = 0.0
		for other in ai_cars:
			if other == current:
				continue
			if other["lane"] != current["lane"]:
				continue
			var gap = other["distance"] - current["distance"]
			if gap > 0 and gap < closest_gap:
				closest_gap = gap
		if closest_gap < draft_distance:
			intensity = 1.0 - (closest_gap / draft_distance)
		var ai = current["car"] as Car
		ai.apply_draft_bonus(delta, intensity)
		current["draft_intensity"] = intensity

func is_lane_clear(car: Car, target_lane: int, safety_distance: float = 120.0) -> bool:
	var my_dist := car.is_player ? 0.0 : car.distance_ahead
	for entry in ai_cars:
		if entry["lane"] != target_lane:
			continue
		var gap = abs(entry["distance"] - my_dist)
		if gap < safety_distance:
			return false
	return true

func is_lane_clear_for_player(target_lane: int, safety_distance: float = 120.0) -> bool:
	return is_lane_clear(player_car, target_lane, safety_distance)

func _apply_side_drafting(delta: float) -> void:
	for a_i in range(ai_cars.size()):
		var A = ai_cars[a_i]
		for b_i in range(a_i + 1, ai_cars.size()):
			var B = ai_cars[b_i]
			if abs(A["lane"] - B["lane"]) != 1:
				continue
			var dz = A["distance"] - B["distance"]
			if abs(dz) > side_draft_range:
				continue
			var t = 1.0 - abs(dz) / side_draft_range
			var tracer: Car
			var victim: Car
			if dz < 0:
				tracer = A["car"]
				victim = B["car"]
			else:
				tracer = B["car"]
				victim = A["car"]
			tracer.side_draft_penalty = max(0.0, tracer.side_draft_penalty - side_draft_strength * t * delta)
			victim.side_draft_penalty = min(victim.side_draft_penalty + side_draft_strength * t * delta, 0.25)

	if player_car:
		for entry in ai_cars:
			if abs(entry["lane"] - player_car.lane_index) != 1:
				continue
			var dzp = entry["distance"] - 0.0
			if abs(dzp) > side_draft_range:
				continue
			var t = 1.0 - abs(dzp) / side_draft_range
			var attacker: Car
			var victim: Car
			if dzp > 0:
				attacker = player_car
				victim = entry["car"]
			else:
				attacker = entry["car"]
				victim = player_car
			attacker.side_draft_penalty = max(0.0, attacker.side_draft_penalty - side_draft_strength * t * delta)
			victim.side_draft_penalty = min(victim.side_draft_penalty + side_draft_strength * t * delta, 0.25)

func _detect_and_resolve_collisions(delta: float) -> void:
	for lane in range(lane_count):
		var lane_entries: Array = []
		for e in ai_cars:
			if e["lane"] == lane:
				lane_entries.append(e)
		if player_car and player_car.lane_index == lane:
			lane_entries.append({
				"car": player_car,
				"lane": lane,
				"distance": 0.0,
				"is_player": true
			})
		lane_entries.sort_custom(Callable(self, "_compare_lane_distance"))

		for i in range(lane_entries.size() - 1):
			var behind = lane_entries[i]
			var ahead = lane_entries[i + 1]
			var car_b: Car = behind["car"]
			var car_a: Car = ahead["car"]
			var gap = ahead["distance"] - behind["distance"]
			if gap > collision_gap:
				continue
			var rel = car_b.speed - car_a.speed
			if rel >= crash_rel_speed_threshold:
				car_a.crash(rel)
				car_b.crash(rel)
			else:
				var transfer = rel * 0.45
				if transfer > 0.0:
					car_a.impact_bump(transfer * 0.65)
					car_b.impact_slow(transfer * 0.35)
			var new_behind_dist = max(ahead["distance"] - collision_gap, behind["distance"] - 2.0)
			behind["distance"] = new_behind_dist
			if not behind.has("is_player"):
				(behind["car"] as Car).set_distance(new_behind_dist)

	if player_car:
		player_car.side_draft_penalty = max(0.0, player_car.side_draft_penalty - 0.5 * delta)
	for e in ai_cars:
		var c: Car = e["car"]
		c.side_draft_penalty = max(0.0, c.side_draft_penalty - 0.5 * delta)

func _compare_lane_distance(a, b) -> int:
	if a["distance"] < b["distance"]:
		return -1
	elif a["distance"] > b["distance"]:
		return 1
	return 0

func _update_ai_lane_changes(delta: float) -> void:
	for car_data in ai_cars:
		car_data["lane_change_timer"] = max(car_data["lane_change_timer"] - delta, 0.0)
		if car_data["lane_change_timer"] > 0.0:
			continue
		var current_lane = car_data["lane"]
		var current_gap = _lane_ahead_gap(current_lane, car_data["distance"])
		if current_gap > lane_change_threshold:
			continue
		var best_lane = current_lane
		var best_score = _lane_change_score(current_lane, car_data["distance"], current_gap)
		for lane_index in range(lane_count):
			if lane_index == current_lane:
				continue
			var gap = _lane_ahead_gap(lane_index, car_data["distance"])
			var score = _lane_change_score(lane_index, car_data["distance"], gap)
			if score > best_score + 5:
				best_score = score
				best_lane = lane_index
		if best_lane != current_lane:
			car_data["lane"] = best_lane
			car_data["lane_change_timer"] = lane_change_interval

func _lane_change_score(lane_index: int, distance: float, gap: float) -> float:
	var ahead_count = _lane_nearby_count(lane_index, distance)
	var base_gap = gap
	if base_gap <= 0.0:
		base_gap = pack_snapshot_range * 0.5
	return base_gap - float(ahead_count) * 12.0

func _lane_ahead_gap(lane_index: int, distance: float) -> float:
	var closest_gap = pack_snapshot_range
	for other in ai_cars:
		if other["lane"] != lane_index:
			continue
		var diff = other["distance"] - distance
		if diff > 2.5 and diff < closest_gap:
			closest_gap = diff
	return closest_gap

func _lane_nearby_count(lane_index: int, distance: float) -> int:
	var count = 0
	for other in ai_cars:
		if other["lane"] != lane_index:
			continue
		if abs(other["distance"] - distance) <= draft_distance:
			count += 1
	return count

func _is_racing() -> bool:
	if race_controller == null:
		return true
	if race_controller.has_method("is_racing"):
		return race_controller.is_racing()
	return true

func _hold_grid(delta: float) -> void:
	var grid_speed = player_car.min_speed * 0.45
	if player_car:
		player_car.hold_speed(grid_speed, delta)
	for car_data in ai_cars:
		var ai = car_data["car"] as Car
		ai.hold_speed(grid_speed, delta)

func _update_player_draft() -> void:
	player_draft_intensity = 0.0
	player_closest_gap = pack_snapshot_range
	var player_lane = player_car.lane_index
	for car_data in ai_cars:
		if car_data["lane"] != player_lane:
			continue
		var gap = car_data["distance"]
		if gap <= 0 or gap >= draft_distance:
			continue
		var intensity = 1.0 - (gap / draft_distance)
		player_draft_intensity = max(player_draft_intensity, intensity)
		player_closest_gap = min(player_closest_gap, gap)
	if player_closest_gap > draft_distance:
		player_closest_gap = draft_distance
	if player_car:
		player_car.draft_effect_intensity = player_draft_intensity

func get_player_draft_stats() -> Dictionary:
	return {
		"draft": player_draft_intensity,
		"gap": player_closest_gap
	}
