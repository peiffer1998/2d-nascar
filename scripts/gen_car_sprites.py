from pathlib import Path
from PIL import Image, ImageDraw

assets = Path('assets')
assets.mkdir(exist_ok=True)

width, height = 64, 128
body_padding = 8
roof_height = 26
window_height = 14

colors = {
    'car_blue': (48, 120, 230),
    'car_yellow': (255, 200, 45),
    'car_red': (210, 45, 55),
    'car_gray': (160, 160, 180)
}

def create_car_image(name, base_color):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    body = (8, 18, width - 8, height - 14)
    draw.rounded_rectangle(body, radius=14, fill=base_color)
    stripe = (width * 0.5 - 6, 18, width * 0.5 + 6, height - 14)
    draw.rectangle(stripe, fill=(255, 255, 255, 120))
    top_roof = (width * 0.2, 24, width * 0.8, 24 + roof_height)
    draw.rectangle(top_roof, fill=(86, 110, 140, 220))
    window_y = 30
    window = (width * 0.25, window_y, width * 0.75, window_y + window_height)
    draw.rectangle(window, fill=(195, 220, 240, 200))
    light_w = 10
    draw.rectangle((body[0] + 6, body[3] - 20, body[0] + 6 + light_w, body[3] - 10), fill=(255, 255, 200))
    draw.rectangle((body[2] - 6 - light_w, body[3] - 20, body[2] - 6, body[3] - 10), fill=(255, 255, 200))
    draw.rectangle((body[0] + 6, body[1] + 6, body[0] + 6 + light_w, body[1] + 12), fill=(255, 255, 255))
    draw.rectangle((body[2] - 6 - light_w, body[1] + 6, body[2] - 6, body[1] + 12), fill=(255, 255, 255))
    outline = (body[0], body[1], body[2], body[3])
    draw.rounded_rectangle(outline, radius=14, outline=(18, 18, 18), width=2)
    target = assets / f'{name}.png'
    img.save(target)
    print('Wrote', target)

if __name__ == '__main__':
    for name, color in colors.items():
        create_car_image(name, color)
