from fastapi.responses import FileResponse

import gphoto2 as gp

camera = None


def get_camera():
    global camera
    if camera is None:
        try:
            camera = gp.Camera()
            camera.init()
        except Exception:
            camera = None
    return camera


def get_settings():
    return get_camera().get_settings()


def set_viewfinder():
    get_camera().set_viewfinder(True)


def enable_viewfinder():
    get_camera().enable_viewfinder()


def disable_viewfinder():
    get_camera().disable_viewfinder()

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

