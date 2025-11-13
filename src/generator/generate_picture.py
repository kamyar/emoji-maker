import math
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

# Wolt fonts
FONT_WOLT_BLACK = "src/generator/fonts/Omnes-Black.otf"
FONT_WOLT_MEDIUM = "src/generator/fonts/Omnes-Medium.otf"
FONT_WOLT_REGULAR = "src/generator/fonts/Omnes-Regular.otf"
FONT_WOLT_SEMIBOLD = "src/generator/fonts/Omnes-Semibold.otf"
FONT_WOLT_COND_BLACK = "src/generator/fonts/OmnesCond-Black.otf"

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


def convert_to_hdr(image_input):
    """Convert an image to HDR format while preserving transparency
    Args:
        image_input: Either a PIL Image or BytesIO containing an image
    Returns:
        BytesIO: HDR version of the image
    """
    # Convert input to PIL Image if needed
    if isinstance(image_input, BytesIO):
        img = Image.open(image_input)
    else:
        img = image_input

    # Split into RGB and alpha channels
    rgb = img.convert("RGB")
    alpha = img.split()[-1]  # Get alpha channel

    # Convert RGB to numpy array
    img_array = np.array(rgb)

    # Convert to float32 and normalize
    float_array = img_array.astype(np.float32) / 255.0

    # Enhance brightness and contrast
    enhanced = np.power(float_array, 0.85) * 1.5

    # Convert back to 8-bit
    enhanced_8bit = (np.clip(enhanced, 0, 1) * 255).astype(np.uint8)

    # Convert back to PIL Image and reapply alpha
    enhanced_img = Image.fromarray(enhanced_8bit, mode="RGB")
    enhanced_img.putalpha(alpha)

    # Save as PNG
    out = BytesIO()
    enhanced_img.save(out, format="PNG")
    out.seek(0)
    return out


def generate_image(input: GenerateInput):
    text = input.text.upper()

    # Select font and color based on platform
    if input.platform == "deliveroo":
        font_path = FONT_DELIVEROO_SEMIBOLD
        color = COLOR_RGB_DELIVEROO
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
