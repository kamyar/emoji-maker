import os
import uuid
import logging
import time
import contextvars

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.generator.generate_picture import (GenerateInput, generate_image,
                                            make_gif)
from src.generator.generate_3d_text import Generate3DInput, generate_3d_text, generate_3d_both
from src.generator.font_manager import get_available_fonts

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='-')

class TraceFormatter(logging.Formatter):
    def format(self, record):
        record.trace_id = trace_id_var.get('-')
        return super().format(record)

handler = logging.StreamHandler()
handler.setFormatter(TraceFormatter(
    '%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s'
))
logging.basicConfig(level=logging.DEBUG, handlers=[handler])
logger = logging.getLogger("app")

app = FastAPI()

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    tid = uuid.uuid4().hex[:8]
    trace_id_var.set(tid)
    logger.info(">> %s %s", request.method, request.url.path)
    t0 = time.time()
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    logger.info("<< %s %s %d (%.0fms)", request.method, request.url.path, response.status_code, elapsed)
    return response

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
        logger.debug("generate-3d input: text=%r font=%s fontSize=%.1f gap=%.1f outline=%s outlineWidth=%.1f border=%s fill=%s scale=%.1f",
                     data.text, data.font, data.fontSize, data.gap, data.addOutline, data.outlineWidth,
                     data.addBorder, data.fillBorder, data.scale)
        result = generate_3d_both(data)
        import re
        safe_name = re.sub(r'[^\w\s-]', '', data.text.split("\n")[0][:20]).strip().replace(' ', '_')

        file_id = str(uuid.uuid4())
        _temp_files[f"{file_id}.3mf"] = result.mf_buf.getvalue()
        _temp_files[f"{file_id}.stl"] = result.combined_stl.getvalue()
        _temp_files[f"{file_id}.text.stl"] = result.text_stl.getvalue()
        if result.border_stl:
            _temp_files[f"{file_id}.border.stl"] = result.border_stl.getvalue()

        while len(_temp_files) > 60:
            oldest = next(iter(_temp_files))
            del _temp_files[oldest]

        if data.exportFormat == "3mf":
            content = _temp_files[f"{file_id}.3mf"]
            media_type = "model/3mf"
        else:
            content = _temp_files[f"{file_id}.stl"]
            media_type = "model/stl"

        headers = {
            "Content-Disposition": f'attachment; filename="{safe_name}.{data.exportFormat}"',
            "X-Model-Width": str(result.dimensions.width),
            "X-Model-Height": str(result.dimensions.height),
            "X-Model-Depth": str(result.dimensions.depth),
            "X-Bambu-File-Id": file_id,
            "X-Stl-File-Id": file_id,
            "X-Text-Stl-Id": file_id,
            "Access-Control-Expose-Headers": "X-Model-Width, X-Model-Height, X-Model-Depth, X-Bambu-File-Id, X-Stl-File-Id, X-Text-Stl-Id, X-Border-Stl-Id",
        }
        if result.border_stl:
            headers["X-Border-Stl-Id"] = file_id

        logger.info("generate-3d ok: %s %.1fx%.1fx%.1fmm",
                    data.exportFormat, result.dimensions.width, result.dimensions.height, result.dimensions.depth)
        return Response(content=content, media_type=media_type, headers=headers)
    except Exception as e:
        logger.exception("generate-3d failed")
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


@api_app.get("/temp-stl/{file_id}/{part}")
async def download_temp_stl_part(file_id: str, part: str):
    key = f"{file_id}.{part}.stl"
    data = _temp_files.get(key)
    if not data:
        return JSONResponse(status_code=404, content={"error": "File not found or expired"})
    return Response(
        content=data,
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="{part}.stl"'},
    )
