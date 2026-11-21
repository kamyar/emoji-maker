#!/usr/bin/env python3
"""Test the 2D generation endpoint without a network listener."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import api_app


async def generate_request(text, *, gif=False):
    events = []
    payload = json.dumps({"text": text, "gif": gif}).encode()

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(event):
        events.append(event)

    await api_app(
        {
            "type": "http", "method": "POST", "path": "/generate", "root_path": "",
            "scheme": "http", "http_version": "1.1", "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
        send,
    )
    status = events[0]["status"]
    content_type = dict(events[0]["headers"])[b"content-type"]
    body = b"".join(event.get("body", b"") for event in events[1:])
    return status, content_type, body


class GenerateTextLimitTest(unittest.TestCase):
    def test_png_accepts_exactly_150_characters(self):
        text = "\n".join(["A" * 30, "B" * 30, "C" * 30, "D" * 30, "E" * 26])
        self.assertEqual(len(text), 150)
        status, content_type, body = asyncio.run(generate_request(text))
        self.assertEqual((status, content_type), (200, b"image/png"))
        with Image.open(BytesIO(body)) as image:
            self.assertEqual((image.format, image.size), ("PNG", (256, 256)))
            self.assertIsNotNone(image.getbbox())

    def test_gif_accepts_exactly_150_characters(self):
        text = "Test phrase " * 12 + "sample"
        self.assertEqual(len(text), 150)
        status, content_type, body = asyncio.run(generate_request(text, gif=True))
        self.assertEqual((status, content_type), (200, b"image/gif"))
        with Image.open(BytesIO(body)) as image:
            self.assertEqual((image.format, image.size), ("GIF", (256, 256)))
            self.assertGreater(image.n_frames, 1)

    def test_rejects_151_characters_including_line_breaks(self):
        for gif in (False, True):
            with self.subTest(gif=gif):
                status, content_type, body = asyncio.run(generate_request("A" * 149 + "\nB", gif=gif))
                self.assertEqual((status, content_type), (422, b"application/json"))
                self.assertEqual(json.loads(body), {"detail": "Text must be 150 characters or fewer."})


if __name__ == "__main__":
    unittest.main()
