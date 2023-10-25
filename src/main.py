import html
import os

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.generator.generate_picture import generate_image

app = FastAPI()


api_app = FastAPI()

app.mount("/api", api_app)

app.mount(
    "/",
    StaticFiles(
        directory=os.path.join(os.path.dirname(__file__), "..", "static"),
        html=True,
    ),
    name="static",
)


@api_app.get("/generate")
async def generate(text: str):
    image_buffer = generate_image(text)
    return Response(content=image_buffer.getvalue(), media_type="image/png")
    # return StreamingResponse(content=image_buffer.getvalue(), media_type="image/png")
