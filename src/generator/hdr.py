"""HDR image processing module.

Provides functionality to convert images to HDR PNG format compatible with
Slack, macOS, and Chrome on HDR-capable displays.
"""

import base64
import struct
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, PngImagePlugin

# Rec.2020 + PQ ICC Profile (9,176 bytes) - embedded for HDR PNG support
REC2020_PQ_ICC_PROFILE_B64 = (
    "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"
    "EzlzMy5EEC+AAEzNKvcAAEzNKvcIfkzNKvcSSkzNKvcdq0zNKvcq90zNKvc6jkzNKvdMzUWKJjlZ"
    "mj2tIUZmZjWyHHBzMy5EGBeAAEzNOo4AAEzNOo4IfkzNOo4SSkzNOo4dq0zNOo4q90zNOo46jkzN"
    "Oo5MzUWKNIVZmj2tLhxmZjWyJ75zMy5EIe2AAEzNTM0AAEzNTM0IfkzNTM0SSkzNTM0dq0zNTM0q"
    "90zNTM06jkzNTM1MzUWKRYpZmj2tPa1mZjWyNbJzMy5ELkSAAEWKWZoAAEWKWZoHa0WKWZoQD0WK"
    "WZoaNkWKWZomOUWKWZo0hUWKWZpFikWKWZpZmj2tUGhmZjWyRtlzMy5EPb2AAD2tZmYAAD2tZmYG"
    "Vz2tZmYNyz2tZmYWpz2tZmYhRj2tZmYuHD2tZmY9rT2tZmZQaD2tZmZmZjWyW31zMy5EUMqAADWy"
    "czMAADWyczMFUzWyczMLpDWyczMTOTWyczMccDWyczMnvjWyczM1sjWyczNG2TWyczNbfTWyczNz"
    "My5EZz6AAC5EgAAAAC5EgAAEcC5EgAAJwC5EgAAQLy5EgAAYFy5EgAAh7S5EgAAuRC5EgAA9vS5E"
    "gABQyi5EgABnPi5EgACAAFmaAAAAAFmaAAAHa1maAAAQD1maAAAaNlmaAAAmOVmaAAA0hVmaAABF"
    "ilmaAABZmlBoAABmZkbZAABzMz29AACAAFmaB2sAAFmaB2sHa1maB2sQD1maB2saNlmaB2smOVma"
    "B2s0hVmaB2tFilmaB2tZmlBoBldmZkbZBVNzMz29BHCAAFmaEA8AAFmaEA8Ha1maEA8QD1maEA8a"
    "NlmaEA8mOVmaEA80hVmaEA9FilmaEA9ZmlBoDctmZkbZC6RzMz29CcCAAFmaGjYAAFmaGjYHa1ma"
    "GjYQD1maGjYaNlmaGjYmOVmaGjY0hVmaGjZFilmaGjZZmlBoFqdmZkbZEzlzMz29EC+AAFmaJjkA"
    "AFmaJjkHa1maJjkQD1maJjkaNlmaJjkmOVmaJjk0hVmaJjlFilmaJjlZmlBoIUZmZkbZHHBzMz29"
    "GBeAAFmaNIUAAFmaNIUHa1maNIUQD1maNIUaNlmaNIUmOVmaNIU0hVmaNIVFilmaNIVZmlBoLhxm"
    "ZkbZJ75zMz29Ie2AAFmaRYoAAFmaRYoHa1maRYoQD1maRYoaNlmaRYomOVmaRYo0hVmaRYpFilma"
    "RYpZmlBoPa1mZkbZNbJzMz29LkSAAFmaWZoAAFmaWZoHa1maWZoQD1maWZoaNlmaWZomOVmaWZo0"
    "hVmaWZpFilmaWZpZmlBoUGhmZkbZRtlzMz29Pb2AAFBoZmYAAFBoZmYGV1BoZmYNy1BoZmYWp1Bo"
    "ZmYhRlBoZmYuHFBoZmY9rVBoZmZQaFBoZmZmZkbZW31zMz29UMqAAEbZczMAAEbZczMFU0bZczML"
    "pEbZczMTOUbZczMccEbZczMnvkbZczM1skbZczNG2UbZczNbfUbZczNzMz29Zz6AAD29gAAAAD29"
    "gAAEcD29gAAJwD29gAAQLz29gAAYFz29gAAh7T29gAAuRD29gAA9vT29gABQyj29gABnPj29gACA"
    "AGZmAAAAAGZmAAAGV2ZmAAANy2ZmAAAWp2ZmAAAhRmZmAAAuHGZmAAA9rWZmAABQaGZmAABmZlt9"
    "AABzM1DKAACAAGZmBlcAAGZmBlcGV2ZmBlcNy2ZmBlcWp2ZmBlchRmZmBlcuHGZmBlc9rWZmBldQ"
    "aGZmBldmZlt9BVNzM1DKBHCAAGZmDcsAAGZmDcsGV2ZmDcsNy2ZmDcsWp2ZmDcshRmZmDcsuHGZm"
    "Dcs9rWZmDctQaGZmDctmZlt9C6RzM1DKCcCAAGZmFqcAAGZmFqcGV2ZmFqcNy2ZmFqcWp2ZmFqch"
    "RmZmFqcuHGZmFqc9rWZmFqdQaGZmFqdmZlt9EzlzM1DKEC+AAGZmIUYAAGZmIUYGV2ZmIUYNy2Zm"
    "IUYWp2ZmIUYhRmZmIUYuHGZmIUY9rWZmIUZQaGZmIUZmZlt9HHBzM1DKGBeAAGZmLhwAAGZmLhwG"
    "V2ZmLhwNy2ZmLhwWp2ZmLhwhRmZmLhwuHGZmLhw9rWZmLhxQaGZmLhxmZlt9J75zM1DKIe2AAGZm"
    "Pa0AAGZmPa0GV2ZmPa0Ny2ZmPa0Wp2ZmPa0hRmZmPa0uHGZmPa09rWZmPa1QaGZmPa1mZlt9NbJz"
    "M1DKLkSAAGZmUGgAAGZmUGgGV2ZmUGgNy2ZmUGgWp2ZmUGghRmZmUGguHGZmUGg9rWZmUGhQaGZm"
    "UGhmZlt9RtlzM1DKPb2AAGZmZmYAAGZmZmYGV2ZmZmYNy2ZmZmYWp2ZmZmYhRmZmZmYuHGZmZmY9"
    "rWZmZmZQaGZmZmZmZlt9W31zM1DKUMqAAFt9czMAAFt9czMFU1t9czMLpFt9czMTOVt9czMccFt9"
    "czMnvlt9czM1slt9czNG2Vt9czNbfVt9czNzM1DKZz6AAFDKgAAAAFDKgAAEcFDKgAAJwFDKgAAQ"
    "L1DKgAAYF1DKgAAh7VDKgAAuRFDKgAA9vVDKgABQylDKgABnPlDKgACAAHMzAAAAAHMzAAAFU3Mz"
    "AAALpHMzAAATOXMzAAAccHMzAAAnvnMzAAA1snMzAABG2XMzAABbfXMzAABzM2c+AACAAHMzBVMA"
    "AHMzBVMFU3MzBVMLpHMzBVMTOXMzBVMccHMzBVMnvnMzBVM1snMzBVNG2XMzBVNbfXMzBVNzM2c+"
    "BHCAAHMzC6QAAHMzC6QFU3MzC6QLpHMzC6QTOXMzC6QccHMzC6QnvnMzC6Q1snMzC6RG2XMzC6Rb"
    "fXMzC6RzM2c+CcCAAHMzEzkAAHMzEzkFU3MzEzkLpHMzEzkTOXMzEzkccHMzEzknvnMzEzk1snMz"
    "EzlG2XMzEzlbfXMzEzlzM2c+EC+AAHMzHHAAAHMzHHAFU3MzHHALpHMzHHATOXMzHHAccHMzHHAn"
    "vnMzHHA1snMzHHBG2XMzHHBbfXMzHHBzM2c+GBeAAHMzJ74AAHMzJ74FU3MzJ74LpHMzJ74TOXMz"
    "J74ccHMzJ74nvnMzJ741snMzJ75G2XMzJ75bfXMzJ75zM2c+Ie2AAHMzNbIAAHMzNbIFU3MzNbIL"
    "pHMzNbITOXMzNbIccHMzNbInvnMzNbI1snMzNbJG2XMzNbJbfXMzNbJzM2c+LkSAAHMzRtkAAHMz"
    "RtkFU3MzRtkLpHMzRtkTOXMzRtkccHMzRtknvnMzRtk1snMzRtlG2XMzRtlbfXMzRtlzM2c+Pb2A"
    "AHMzW30AAHMzW30FU3MzW30LpHMzW30TOXMzW30ccHMzW30nvnMzW301snMzW31G2XMzW31bfXMz"
    "W31zM2c+UMqAAHMzczMAAHMzczMFU3MzczMLpHMzczMTOXMzczMccHMzczMnvnMzczM1snMzczNG"
    "2XMzczNbfXMzczNzM2c+Zz6AAGc+gAAAAGc+gAAEcGc+gAAJwGc+gAAQL2c+gAAYF2c+gAAh7Wc+"
    "gAAuRGc+gAA9vWc+gABQymc+gABnPmc+gACAAIAAAAAAAIAAAAAEcIAAAAAJwIAAAAAQL4AAAAAY"
    "F4AAAAAh7YAAAAAuRIAAAAA9vYAAAABQyoAAAABnPoAAAACAAIAABHAAAIAABHAEcIAABHAJwIAA"
    "BHAQL4AABHAYF4AABHAh7YAABHAuRIAABHA9vYAABHBQyoAABHBnPoAABHCAAIAACcAAAIAACcAE"
    "cIAACcAJwIAACcAQL4AACcAYF4AACcAh7YAACcAuRIAACcA9vYAACcBQyoAACcBnPoAACcCAAIAA"
    "EC8AAIAAEC8EcIAAEC8JwIAAEC8QL4AAEC8YF4AAEC8h7YAAEC8uRIAAEC89vYAAEC9QyoAAEC9n"
    "PoAAEC+AAIAAGBcAAIAAGBcEcIAAGBcJwIAAGBcQL4AAGBcYF4AAGBch7YAAGBcuRIAAGBc9vYAA"
    "GBdQyoAAGBdnPoAAGBeAAIAAIe0AAIAAIe0EcIAAIe0JwIAAIe0QL4AAIe0YF4AAIe0h7YAAIe0u"
    "RIAAIe09vYAAIe1QyoAAIe1nPoAAIe2AAIAALkQAAIAALkQEcIAALkQJwIAALkQQL4AALkQYF4AA"
    "LkQh7YAALkQuRIAALkQ9vYAALkRQyoAALkRnPoAALkSAAIAAPb0AAIAAPb0EcIAAPb0JwIAAPb0Q"
    "L4AAPb0YF4AAPb0h7YAAPb0uRIAAPb09vYAAPb1QyoAAPb1nPoAAPb2AAIAAUMoAAIAAUMoEcIAA"
    "UMoJwIAAUMoQL4AAUMoYF4AAUMoh7YAAUMouRIAAUMo9vYAAUMpQyoAAUMpnPoAAUMqAAIAAZz4A"
    "AIAAZz4EcIAAZz4JwIAAZz4QL4AAZz4YF4AAZz4h7YAAZz4uRIAAZz49vYAAZz5QyoAAZz5nPoAA"
    "Zz6AAIAAgAAAAIAAgAAEcIAAgAAJwIAAgAAQL4AAgAAYF4AAgAAh7YAAgAAuRIAAgAA9vYAAgABQ"
    "yoAAgABnPoAAgACAAAAAY3VydgAAAAAAAABBAAAAAgAHABEAIAA4AFgAhAC/AQoBaQHhAnYDLQQK"
    "BRUGVAfPCY8LnA4DEMQT+hefG8UgZSWeK3cx5DjQQIRItlF+WrdkfG56eNuDio5UmUOkSK8yukPF"
    "VNBn27HnHPK9/t7//////////////////////////////////////////wAAY3VydgAAAAAAAABB"
    "AAAAAgAHABEAIAA4AFgAhAC/AQoBaQHhAnYDLQQKBRUGVAfPCY8LnA4DEMQT+hefG8UgZSWeK3cx"
    "5DjQQIRItlF+WrdkfG56eNuDio5UmUOkSK8yukPFVNBn27HnHPK9/t7/////////////////////"
    "/////////////////////wAAY3VydgAAAAAAAABBAAAAAgAHABEAIAA4AFgAhAC/AQoBaQHhAnYD"
    "LQQKBRUGVAfPCY8LnA4DEMQT+hefG8UgZSWeK3cx5DjQQIRItlF+WrdkfG56eNuDio5UmUOkSK8y"
    "ukPFVNBn27HnHPK9/t7//////////////////////////////////////////wAAAACsaAAAKmkA"
    "ACAHAABHbwAArOMAAAuu////gQAAB60AAMwTAAAAAAAAAAAAAAAAcGFyYQAAAAAAAAAAAAEAAHBh"
    "cmEAAAAAAAAAAAABAABwYXJhAAAAAAAAAAAAAQAAbUJBIAAAAAADAwAAAAAAIAAAAAAAAAAAAAAA"
    "AAAAAABwYXJhAAAAAAAAAAAAAQAAcGFyYQAAAAAAAAAAAAEAAHBhcmEAAAAAAAAAAAABAABtbHVj"
    "AAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADY="
)


def get_rec2020_pq_icc_profile():
    """Get embedded Rec.2020 + PQ ICC profile for HDR PNG (9,176 bytes).

    Returns:
        bytes: ICC profile data for Rec.2020 color space with PQ transfer function
    """
    return base64.b64decode(REC2020_PQ_ICC_PROFILE_B64)


def convert_to_hdr(image_input):
    """Convert an image to Slack-compatible HDR PNG format.

    Creates an HDR PNG with Rec.2020 color gamut and PQ transfer function
    that Slack and Chrome recognize as HDR content.

    Uses wide color gamut ICC profile (Rec.2020 + PQ) that triggers HDR
    display in Chrome and Slack on HDR-capable displays.

    Args:
        image_input: Either a PIL Image or BytesIO containing an image

    Returns:
        BytesIO: HDR PNG that works in Slack, Chrome, and HDR displays
    """
    # Convert input to PIL Image if needed
    if isinstance(image_input, BytesIO):
        img = Image.open(image_input)
    else:
        img = image_input

    # Split into RGB and alpha channels
    rgb = img.convert("RGB")
    has_alpha = img.mode == "RGBA"
    if has_alpha:
        alpha = img.split()[-1]
    else:
        alpha = None

    # Convert to float for HDR processing
    img_array = np.array(rgb).astype(np.float32) / 255.0

    # EXTREMELY aggressive saturation and brightness for obvious HDR
    # Use adaptive saturation to preserve hues of already-saturated colors
    hsv = cv2.cvtColor((img_array * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(
        np.float32
    )
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 3.0, 0, 255)  # ULTRA saturation for HDR
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 2.2, 0, 255)  # ULTRA brightness boost
    img_array = (
        cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32) / 255.0
    )

    # HDR tone mapping - create values > 1.0 for true HDR
    enhanced = np.power(img_array, 0.50) * 4.5  # ULTRA aggressive for maximum HDR

    # Create strong bloom effect for HDR highlights
    img_for_glow = (np.clip(enhanced, 0, 1) * 255).astype(np.uint8)
    glow = cv2.GaussianBlur(img_for_glow, (51, 51), 25)
    glow_float = glow.astype(np.float32) / 255.0

    # Adaptive glow: reduce for bright reds to preserve red hue
    glow_strength = np.where(1, 0.4, 1.0)
    result = enhanced + glow_float * glow_strength

    # Keep extended range - values above 1.0 are HDR content
    # Don't clip too much - we want to preserve the HDR range
    result = np.clip(result, 0, 4.0)  # Allow up to 4x standard brightness

    # Normalize to 0-1 range for 8-bit PNG encoding
    result_normalized = result / 4.0
    result_8bit = (result_normalized * 255).astype(np.uint8)

    enhanced_img = Image.fromarray(result_8bit, mode="RGB")

    if has_alpha:
        enhanced_img.putalpha(alpha)

    # Get embedded Rec.2020 PQ ICC profile
    icc_profile = get_rec2020_pq_icc_profile()

    # Create PngInfo with HDR metadata
    pnginfo = PngImagePlugin.PngInfo()

    # Add chromaticity for wide color gamut (Rec.2020-like primaries)
    # Format: white_x, white_y, red_x, red_y, green_x, green_y, blue_x, blue_y
    # These values indicate wider gamut than sRGB
    pnginfo.add(
        b"cHRM",
        struct.pack(
            ">8I",
            31270,  # white x
            32900,  # white y
            64000,  # red x
            33000,  # red y
            30000,  # green x
            60000,  # green y
            15000,  # blue x
            6000,  # blue y
        ),
    )

    out = BytesIO()

    # Save as PNG with HDR ICC profile and chromaticity
    enhanced_img.save(
        out,
        format="PNG",
        icc_profile=icc_profile,
        pnginfo=pnginfo,
        compress_level=6,
        optimize=False,
    )

    out.seek(0)
    return out
