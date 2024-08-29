import os

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from src.generator.generate_picture import GenerateInput, generate_image, make_gif

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


@api_app.post("/generate")
async def generate(data: GenerateInput):
    if len(data.text) > 30:
        return "Nope"
    if data.gif:
        image_buffer = make_gif(data)
        return Response(content=image_buffer.getvalue(), media_type="image/gif")
    image_buffer = generate_image(data)
    return Response(content=image_buffer.getvalue(), media_type="image/png")
    # return StreamingResponse(content=image_buffer.getvalue(), media_type="image/png")
