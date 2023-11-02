from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

FONT_OMNES_BLACK = "src/generator/fonts/Omnes-Black.otf"
FONT_OMNES_MEDIUM = "src/generator/fonts/Omnes-Medium.otf"
FONT_OMNES_REGULAR = "src/generator/fonts/Omnes-Regular.otf"
FONT_OMNES_SEMIBOLD = "src/generator/fonts/Omnes-Semibold.otf"
FONT_OMNES_COND_BLACK = "src/generator/fonts/OmnesCond-Black.otf"
FONTS = [
    FONT_OMNES_BLACK,
    # FONT_OMNES_COND_BLACK,
]

FONT_SIZE_INITIAL = 160


def fonts_with_size(font_path: str, font_size: int):
    return ImageFont.truetype(font_path, size=font_size)


image_width = 256
image_height = 256

# raw_text = input().replace("\\n", "\n")
# message = raw_text.upper()

# COLOR = "009de0"
# COLOR2 = "00cde8"
COLOR_RGB = (0, 157, 224)


# COLOR_RGB2 = (0, 205, 232)
class GenerateInput(BaseModel):
    text: str
    gif: bool = False


def generate_image(input: GenerateInput):
    text = input.text.upper()
    # for font_path in FONTS:
    font_path = FONT_OMNES_COND_BLACK
    img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
    font_size = FONT_SIZE_INITIAL

    x_start = 0
    y_start = 0
    while font_size > 1:
        imgDraw = ImageDraw.Draw(img)
        font = fonts_with_size(font_path, font_size)
        bbox = imgDraw.textbbox((0, 0), text, font)
        # bbox[2] - bbox[0]  # Right x-coordinate - Left x-coordinate
        text_width = bbox[-2]
        # bbox[3] - bbox[1]  # Lower y-coordinate - Upper y-coordinate
        text_height = bbox[-1]
        if text_width + 2 <= image_width and text_height + 2 <= image_height:
            x_start = (image_width - text_width) / 2
            y_start = (image_height - text_height) / 2
            break
        font_size -= 2

    font = fonts_with_size(font_path, font_size)
    imgDraw.text(
        (x_start, y_start),
        text,
        font=font,
        fill=COLOR_RGB,
        align="center",
    )
    image_buffer = BytesIO()
    img.save(image_buffer, format="PNG")
    return image_buffer


def make_gif(input: GenerateInput):
    text = input.text.upper()
    # for font_path in FONTS:
    font_path = FONT_OMNES_COND_BLACK
    font_size = FONT_SIZE_INITIAL
    frames = []
    for i in range(len(text) + 1):
        partial_text = text[:i]
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        x_start = 0
        y_start = 0
        imgDraw = ImageDraw.Draw(img)
        while font_size > 1:
            imgDraw = ImageDraw.Draw(img)
            font = fonts_with_size(font_path, font_size)
            bbox = imgDraw.textbbox((0, 0), partial_text, font)
            # bbox[2] - bbox[0]  # Right x-coordinate - Left x-coordinate
            text_width = bbox[-2]
            # bbox[3] - bbox[1]  # Lower y-coordinate - Upper y-coordinate
            text_height = bbox[-1]
            if text_width <= image_width and text_height <= image_height:
                x_start = (image_width - text_width) / 2
                y_start = (image_height - text_height) / 2
                break
            font_size -= 2

        font = fonts_with_size(font_path, font_size)
        imgDraw.text(
            (x_start, y_start),
            partial_text,
            font=font,
            fill=COLOR_RGB,
            align="center",
        )
        frames.append(img.copy())

    image_buffer = BytesIO()
    frames[0].save(
        image_buffer,
        format="GIF",
        append_images=frames[2:],
        save_all=True,
        duration=75,
        loop=0,
        interlace=False,
        disposal=2,
    )
    return image_buffer
