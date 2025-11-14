import math
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from src.generator.hdr import convert_to_hdr

# Wolt fonts
FONT_WOLT_BLACK = "src/generator/fonts/Omnes-Black.otf"
FONT_WOLT_MEDIUM = "src/generator/fonts/Omnes-Medium.otf"
FONT_WOLT_REGULAR = "src/generator/fonts/Omnes-Regular.otf"
FONT_WOLT_SEMIBOLD = "src/generator/fonts/Omnes-Semibold.otf"
FONT_WOLT_COND_BLACK = "src/generator/fonts/OmnesCond-Black.otf"

# Doordash fonts
FONT_DOORDASH_BOLD = "src/generator/fonts/TTNorms-Bold.woff2"

# Deliveroo fonts
FONT_DELIVEROO_SEMIBOLD = "src/generator/fonts/stratos-semibold.woff2"

FONTS_WOLT = [
    FONT_WOLT_BLACK,
    # FONT_WOLT_COND_BLACK,
]

FONT_SIZE_INITIAL = 160


def fonts_with_size(font_path: str, font_size: int):
    return ImageFont.truetype(font_path, size=font_size)


image_width = 256
image_height = 256

# raw_text = input().replace("\\n", "\n")
# message = raw_text.upper()

# Platform colors
COLOR_RGB_WOLT = (0, 157, 224)
COLOR_RGB_DOORDASH = (255, 48, 8)  # #FF3008
COLOR_RGB_DELIVEROO = (0, 205, 188)  # #00CDBC


# COLOR_RGB2 = (0, 205, 232)
class GenerateInput(BaseModel):
    text: str
    gif: bool = False
    margin: int = 0
    loop: bool = True
    frameDelay: int = 200
    hdr: bool = False
    platform: str = "wolt"  # "wolt" or "deliveroo"


def generate_image(input: GenerateInput):
    text = input.text.upper()

    # Select font and color based on platform
    if input.platform == "deliveroo":
        font_path = FONT_DELIVEROO_SEMIBOLD
        color = COLOR_RGB_DELIVEROO
    elif input.platform == "doordash":
        font_path = FONT_DOORDASH_BOLD
        color = COLOR_RGB_DOORDASH
    else:  # Default to wolt
        font_path = FONT_WOLT_COND_BLACK
        color = COLOR_RGB_WOLT

    img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))

    font_size = FONT_SIZE_INITIAL
    x_start = 0
    y_start = 0
    while font_size > 1:
        imgDraw = ImageDraw.Draw(img)
        font = fonts_with_size(font_path, font_size)
        bbox = imgDraw.textbbox((0, 0), text, font)
        text_width = bbox[-2]
        text_height = bbox[-1]
        if (
            text_width + input.margin <= image_width
            and text_height + input.margin <= image_height
        ):
            x_start = (image_width - text_width) / 2
            y_start = (image_height - text_height) / 2
            break
        font_size -= 2

    font = fonts_with_size(font_path, font_size)
    imgDraw.text(
        (x_start, y_start),
        text,
        font=font,
        fill=color,
        align="center",
    )

    if input.hdr:
        return convert_to_hdr(img)
    else:
        image_buffer = BytesIO()
        img.save(image_buffer, format="PNG")
        return image_buffer


def make_gif(input: GenerateInput):
    text = input.text.upper()

    # Select font and color based on platform
    if input.platform == "deliveroo":
        font_path = FONT_DELIVEROO_SEMIBOLD
        color = COLOR_RGB_DELIVEROO
    elif input.platform == "doordash":
        font_path = FONT_DOORDASH_BOLD
        color = COLOR_RGB_DOORDASH
    else:  # Default to wolt
        font_path = FONT_WOLT_COND_BLACK
        color = COLOR_RGB_WOLT

    font_size = FONT_SIZE_INITIAL
    frames = []
    for i in range(len(text) + 1):
        partial_text = text[:i]
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        x_start = 0
        y_start = 0
        while font_size > 1:
            imgDraw = ImageDraw.Draw(img)
            font = fonts_with_size(font_path, font_size)
            bbox = imgDraw.textbbox((0, 0), partial_text, font)
            text_width = bbox[-2]
            text_height = bbox[-1]
            if (
                text_width + input.margin <= image_width
                and text_height + input.margin <= image_height
            ):
                x_start = (image_width - text_width) / 2
                y_start = (image_height - text_height) / 2
                break
            font_size -= 2

        font = fonts_with_size(font_path, font_size)
        imgDraw.text(
            (x_start, y_start),
            partial_text,
            font=font,
            fill=color,
            align="center",
        )

        if input.hdr:
            # Convert frame to HDR and back to PIL Image for GIF
            hdr_buffer = convert_to_hdr(img)
            hdr_frame = Image.open(hdr_buffer)
            frames.append(hdr_frame.copy())
        else:
            frames.append(img.copy())

    image_buffer = BytesIO()
    frames[0].save(
        image_buffer,
        format="GIF",
        append_images=frames[1:],
        save_all=True,
        duration=input.frameDelay,
        loop=0 if input.loop else 1,
        interlace=False,
        disposal=2,
    )
    return image_buffer
