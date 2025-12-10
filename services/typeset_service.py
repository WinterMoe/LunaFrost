import os
import math
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONTS = [
    {"name": "DejaVuSans", "path": None},                           
]

def load_font(fonts_root, font_name=None, font_size=24):
                                                       
    if font_name:
        if fonts_root:
            candidate = os.path.join(fonts_root, f"{font_name}.ttf")
            if os.path.exists(candidate):
                try:
                    return ImageFont.truetype(candidate, font_size)
                except Exception:
                    pass
                                     
        if os.path.exists(font_name):
            try:
                return ImageFont.truetype(font_name, font_size)
            except Exception:
                pass
                         
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()

def measure_text(draw, text, font):
                                                                         
    if not text:
        return (0, 0)
    bbox = draw.textbbox((0, 0), text, font=font)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])

def wrap_text(draw, text, font, max_width, line_height):
                                                                   
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        w, _ = measure_text(draw, trial, font)
        if w <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_text_in_box(draw, bbox, text, font, fill, stroke_fill, stroke_width, line_height=1.2, align="center", valign="middle", is_vertical=False):
    x, y, w, h = bbox
    if is_vertical:
                                                        
        chars = list(text)
        max_chars = max(1, len(chars))
                                 
        line_height_px = int(font.size * line_height)
        total_height = line_height_px * max_chars
        start_y = y
        if valign == "middle":
            start_y = y + max(0, (h - total_height) // 2)
        elif valign == "bottom":
            start_y = y + max(0, h - total_height)
        current_y = start_y
        for ch in chars:
            draw.text((x + w // 2, current_y), ch, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill, anchor="mm")
            current_y += line_height_px
        return

                       
    lines = wrap_text(draw, text, font, w, line_height)
    line_height_px = int(font.size * line_height)
    total_height = line_height_px * len(lines)
    if valign == "middle":
        start_y = y + max(0, (h - total_height) // 2)
    elif valign == "bottom":
        start_y = y + max(0, h - total_height)
    else:
        start_y = y

    for i, line in enumerate(lines):
        lw, _ = measure_text(draw, line, font)
        if align == "left":
            tx = x
        elif align == "right":
            tx = x + max(0, w - lw)
        else:
            tx = x + max(0, (w - lw) // 2)
        ty = start_y + i * line_height_px
        draw.text((tx, ty), line, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

def apply_strokes(base_img, strokes):
                                             
    if not strokes:
        return base_img
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    for stroke in strokes:
        mode = stroke.get("mode", "paint")
        color = stroke.get("color", "#FFFFFF" if mode == "erase" else "#FFFFFF")
        size = int(stroke.get("size", 12) or 12)
        pts = stroke.get("points") or []
        if len(pts) < 2:
            continue
                       
        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i + 1]
            try:
                draw.line([tuple(p1), tuple(p2)], fill=color, width=size)
            except Exception:
                continue
    return img

def render_typeset_image(original_path, output_path, overrides, fonts_root=None):
           
    if not os.path.exists(original_path):
        raise FileNotFoundError(f"Original image not found: {original_path}")

    regions = (overrides or {}).get("regions") or []
    strokes = (overrides or {}).get("strokes") or []

    with Image.open(original_path) as im:
        im = im.convert("RGBA")
        im = apply_strokes(im, strokes)
        draw = ImageDraw.Draw(im)

        for region in regions:
            bbox = region.get("bbox") or []
            if len(bbox) != 4:
                continue
            text = (region.get("user_text") or "").strip()
            if not text:
                continue
            font_family = region.get("font_family")
            font_size = int(region.get("font_size") or 24)
            color = region.get("color") or "#000000"
            stroke_color = region.get("stroke_color") or "#FFFFFF"
            stroke_width = int(region.get("stroke_width") or 0)
            line_height = float(region.get("line_height") or 1.2)
            align = region.get("align") or "center"
            valign = region.get("vertical_align") or "middle"
            is_vertical = bool(region.get("is_vertical"))

            font = load_font(fonts_root, font_family, font_size)
            draw_text_in_box(
                draw,
                bbox,
                text,
                font=font,
                fill=color,
                stroke_fill=stroke_color,
                stroke_width=stroke_width,
                line_height=line_height,
                align=align,
                valign=valign,
                is_vertical=is_vertical
            )

                                                                
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        ext = os.path.splitext(output_path)[1].lower()
        if ext == ".webp":
            im.save(output_path, format="WEBP", lossless=True, method=6)
        else:
            im.save(output_path, format="PNG", optimize=True)

    return output_path

