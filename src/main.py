import os
import uuid

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.generator.generate_picture import (GenerateInput, generate_image,
                                            make_gif)
from src.generator.generate_3d_text import Generate3DInput, generate_3d_text, generate_3d_both
from src.generator.font_manager import get_available_fonts

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

_temp_files: dict[str, bytes] = {}

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
    
    # Generate PNG (with HDR metadata if hdr=True)
    image_buffer = generate_image(data)
    return Response(content=image_buffer.getvalue(), media_type="image/png")


@api_app.get("/fonts")
async def list_fonts():
    fonts = get_available_fonts()
    return {"fonts": list(fonts.keys())}


@api_app.post("/generate-3d")
async def generate_3d(data: Generate3DInput):
    try:
        stl_buf, mf_buf, dimensions = generate_3d_both(data)
        safe_name = data.text.split("\n")[0][:20].replace(" ", "_")

        file_id = str(uuid.uuid4())
        _temp_files[f"{file_id}.3mf"] = mf_buf.getvalue()
        _temp_files[f"{file_id}.stl"] = stl_buf.getvalue()

        while len(_temp_files) > 40:
            oldest = next(iter(_temp_files))
            del _temp_files[oldest]

        if data.exportFormat == "3mf":
            content = _temp_files[f"{file_id}.3mf"]
            media_type = "model/3mf"
        else:
            content = _temp_files[f"{file_id}.stl"]
            media_type = "model/stl"

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}.{data.exportFormat}"',
                "X-Model-Width": str(dimensions.width),
                "X-Model-Height": str(dimensions.height),
                "X-Model-Depth": str(dimensions.depth),
                "X-Bambu-File-Id": file_id,
                "Access-Control-Expose-Headers": "X-Model-Width, X-Model-Height, X-Model-Depth, X-Bambu-File-Id, X-Stl-File-Id",
                "X-Stl-File-Id": file_id,
            },
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@api_app.get("/temp-3mf/{file_id}")
async def download_temp_3mf(file_id: str):
    data = _temp_files.get(f"{file_id}.3mf")
    if not data:
        return JSONResponse(status_code=404, content={"error": "File not found or expired"})
    return Response(
        content=data,
        media_type="model/3mf",
        headers={"Content-Disposition": f'attachment; filename="model.3mf"'},
    )


@api_app.get("/temp-stl/{file_id}")
async def download_temp_stl(file_id: str):
    data = _temp_files.get(f"{file_id}.stl")
    if not data:
        return JSONResponse(status_code=404, content={"error": "File not found or expired"})
    return Response(
        content=data,
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="model.stl"'},
    )
