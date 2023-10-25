from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

FONT_OMNES_BLACK = "src/generator/fonts/Omnes-Black.otf"
FONT_OMNES_MEDIUM = "src/generator/fonts/Omnes-Medium.otf"
FONT_OMNES_REGULAR = "src/generator/fonts/Omnes-Regular.otf"
FONT_OMNES_SEMIBOLD = "src/generator/fonts/Omnes-Semibold.otf"
FONT_OMNES_COND_BLACK = "src/generator/fonts/OmnesCond-Black.otf"
FONTS = [
    FONT_OMNES_BLACK,
    FONT_OMNES_COND_BLACK,
]

FONT_SIZE_INITIAL = 56


def fonts_with_size(font_path: str, font_size: int):
    return ImageFont.truetype(font_path, size=font_size)


image_width = 128
image_height = 128
min_margin = 1

# raw_text = input().replace("\\n", "\n")
# message = raw_text.upper()

COLOR = "009de0"
COLOR2 = "00cde8"
COLOR_RGB = (0, 157, 224)
COLOR_RGB2 = (0, 205, 232)


def generate_image(text: str):
    text = text.upper()
    print("Generating image")
    for font_path in FONTS:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        font_size = FONT_SIZE_INITIAL
        x_start = 0
        y_start = 0
        while font_size > 1:
            imgDraw = ImageDraw.Draw(img)
            font = fonts_with_size(font_path, font_size)
            bbox = imgDraw.textbbox((0, 0), text, font)
            # imgDraw.rectangle(bbox, outline="red")
            print(font_size, bbox)
            text_width = bbox[
                -2
            ]  # bbox[2] - bbox[0]  # Right x-coordinate - Left x-coordinate
            text_height = bbox[
                -1
            ]  # bbox[3] - bbox[1]  # Lower y-coordinate - Upper y-coordinate
            if (
                text_width + 2 * min_margin <= image_width
                and text_height + 2 * min_margin <= image_height
            ):
                x_start = (image_width - text_width) / 2
                y_start = (image_height - text_height) / 2
                break
            font_size -= 2

        actual_margin_x = (image_width - text_width) / 2
        actual_margin_y = (image_height - text_height) / 2
        font = fonts_with_size(font_path, font_size)
        # print((margin, margin), text, font, COLOR_RGB)
        # imgDraw.text((0, 0), text, font=font, fill=COLOR_RGB)
        imgDraw.text(
            (x_start, y_start),
            text,
            font=font,
            fill=COLOR_RGB,
            align="center",
        )
        # font_name_text = "-".join(font.getname())
        # filename = f"generated/{'_'.join(raw_text)}_{font_name_text}.png"
        # img.save(filename)
        image_buffer = BytesIO()
        img.save(image_buffer, format="PNG")
        return image_buffer
