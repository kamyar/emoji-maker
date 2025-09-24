import os

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.generator.generate_picture import (GenerateInput, generate_image,
                                            make_gif)

app = FastAPI()

# TMP comment to trigger deploy
# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_app = FastAPI()
app.mount("/api", api_app)

# Serve static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount(
    "/",
    StaticFiles(directory=static_dir, html=True),
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
