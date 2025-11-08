# 2D NASCAR (Python)

This is a standalone Python prototype that replicates the pack-racing logic you had in Godot. It uses `pygame` to draw the three-lane track, handle input, simulate drafting, and show the HUD.

## Setup
1. Install Python 3.11+ (if not already). On macOS you can use `brew install python`.
2. From this repo root run:
   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -r requirements.txt
   ```
3. Launch the game with:
   ```bash
   python3 main.py
   ```

## Controls
- **↑/DOWN**: ↑ is auto full-throttle, ↓ brakes to scrub speed.
- **LEFT/RIGHT**: Move between the three lanes.
- **Enter** (from the menu): Start the selected track.
- **ESC** (during race): Return to the menu.

## Features
- Track menu with presets (3-lane oval, superspeedway, tri-oval).
- Auto-throttle with brake to slow and lane switching.
- Pack spawn with drafting boosts, HUD stats, lap counter, finish banner.
- Simple speed/draft cues built using rectangles and text (no external assets).

If you want a browser-ready experience later, we can export this script via a simple web build or re-implement using Phaser. Let me know if you need that next.
