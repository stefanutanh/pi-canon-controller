import os
import threading
import time
import traceback
import anyio
import gphoto2 as gp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

os.makedirs("static", exist_ok=True)
os.makedirs("captures", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/captures", StaticFiles(directory="captures"), name="captures")

camera = None
camera_lock = threading.Lock()
liveview_active = False


def get_camera():
    global camera
    if camera is None:
        try:
            camera = gp.Camera()
            camera.init()
        except Exception:
            camera = None
            raise
    return camera


def set_viewfinder(cam, value: int):
    try:
        config = cam.get_config()
        try:
            widget = config.get_child_by_name("viewfinder")
            widget.set_value(value)
            cam.set_config(config)
            return True
        except Exception:
            try:
                widget = config.get_child_by_name("eosviewfinder")
                widget.set_value(value)
                cam.set_config(config)
                return True
            except Exception:
                pass
    except Exception as e:
        print(f"Kunde inte ställa in viewfinder till {value}: {e}")
    return False


def enable_viewfinder():
    with camera_lock:
        try:
            cam = get_camera()
            set_viewfinder(cam, 1)
        except Exception:
            global camera
            camera = None


def disable_viewfinder():
    with camera_lock:
        try:
            cam = get_camera()
            set_viewfinder(cam, 0)
        except Exception:
            global camera
            camera = None


@app.get("/")
def read_root():
    return FileResponse("static/index.html")


async def gen_frames(request: Request):
    """Generator för Live View.

    Avslutas när klienten stänger strömmen/fliken eller liveview_active blir False.
    """
    global liveview_active
    try:
        while liveview_active:
            if await request.is_disconnected():
                break

            def capture_preview_sync():
                acquired = camera_lock.acquire(blocking=False)
                if acquired:
                    try:
                        cam = get_camera()
                        camera_file = cam.capture_preview()
                        file_data = camera_file.get_data_and_size()
                        return memoryview(file_data).tobytes()
                    except Exception:
                        global camera
                        camera = None
                        return None
                    finally:
                        camera_lock.release()
                return False

            res = await anyio.to_thread.run_sync(capture_preview_sync)
            if res is None:
                # Fel uppstod, vänta lite och försök igen
                await anyio.sleep(0.1)
            elif res is False:
                # Låset kunde inte erhållas, vänta lite
                await anyio.sleep(0.1)
            else:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + res + b"\r\n"
                )
                await anyio.sleep(0.04)
    finally:
        # Säkerställ att vi stänger av sökaren om loopen bryts
        def stop_lv_sync():
            global camera, liveview_active
            with camera_lock:
                try:
                    cam = get_camera()
                    set_viewfinder(cam, 0)
                except Exception:
                    camera = None
                finally:
                    liveview_active = False
        await anyio.to_thread.run_sync(stop_lv_sync)


@app.get("/api/liveview")
async def liveview_feed(request: Request):
    return StreamingResponse(
        gen_frames(request),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/liveview/start")
def start_liveview():
    global liveview_active, camera
    with camera_lock:
        try:
            cam = get_camera()
            set_viewfinder(cam, 1)
            liveview_active = True
            return {"status": "ok"}
        except Exception as e:
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@app.post("/api/liveview/stop")
def stop_liveview():
    global liveview_active, camera
    with camera_lock:
        try:
            cam = get_camera()
            set_viewfinder(cam, 0)
            liveview_active = False
            return {"status": "ok"}
        except Exception as e:
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@app.get("/api/config")
def get_config():
    with camera_lock:
        try:
            cam = get_camera()
            config = cam.get_config()

            fields = [
                "iso",
                "shutterspeed",
                "aperture",
                "whitebalance",
                "imageformat",
            ]
            data = {}

            for field in fields:
                try:
                    widget = config.get_child_by_name(field)
                    data[field] = {
                        "value": widget.get_value(),
                        "choices": [
                            widget.get_choice(i)
                            for i in range(widget.count_choices())
                        ],
                    }
                except Exception:
                    data[field] = {"value": "N/A", "choices": []}

            return data
        except Exception as e:
            global camera
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


class ConfigUpdate(BaseModel):
    key: str
    value: str


@app.post("/api/config")
def set_config(update: ConfigUpdate):
    with camera_lock:
        try:
            cam = get_camera()
            config = cam.get_config()
            widget = config.get_child_by_name(update.key)
            widget.set_value(update.value)
            cam.set_config(config)
            return {"status": "ok", "key": update.key, "value": update.value}
        except Exception as e:
            global camera
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@app.post("/api/capture")
def capture_image():
    """Standardbildtagning."""
    with camera_lock:
        try:
            cam = get_camera()
            file_path = cam.capture(gp.GP_CAPTURE_IMAGE)
            target_file = f"captures/{file_path.name}"

            camera_file = cam.file_get(
                file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
            )
            camera_file.save(target_file)

            # Om det är en RAW-fil, ladda ner förhandsvisningen som JPEG
            preview_url = f"/captures/{file_path.name}"
            if file_path.name.lower().endswith((".cr2", ".cr3", ".nef", ".arw", ".dng")):
                try:
                    preview_file = cam.file_get(
                        file_path.folder, file_path.name, gp.GP_FILE_TYPE_PREVIEW
                    )
                    preview_name = os.path.splitext(file_path.name)[0] + "_preview.jpg"
                    preview_file.save(f"captures/{preview_name}")
                    preview_url = f"/captures/{preview_name}"
                except Exception as ex:
                    print(f"Kunde inte hämta förhandsvisningsbild: {ex}")

            return {
                "status": "success",
                "filename": file_path.name,
                "url": f"/captures/{file_path.name}",
                "preview_url": preview_url
            }
        except Exception as e:
            global camera
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


class BulbRequest(BaseModel):
    seconds: float


@app.post("/api/bulb")
def bulb_capture(req: BulbRequest):
    """Långtidsexponering (Bulb) för nattfotografering."""
    with camera_lock:
        try:
            cam = get_camera()
            config = cam.get_config()

            # Spara ursprunglig slutartid och ställ in bulb
            shutterspeed_widget = config.get_child_by_name("shutterspeed")
            original_shutterspeed = shutterspeed_widget.get_value()

            bulb_val = None
            choices = [
                shutterspeed_widget.get_choice(i)
                for i in range(shutterspeed_widget.count_choices())
            ]
            for choice in choices:
                if choice.lower() == "bulb":
                    bulb_val = choice
                    break

            if bulb_val:
                shutterspeed_widget.set_value(bulb_val)
                cam.set_config(config)
                # Eftersom vi ändrat config, hämta den på nytt för nästa steg
                config = cam.get_config()
                release_widget = config.get_child_by_name("eosremoterelease")
            else:
                raise Exception(
                    "Kameran stödjer inte BULB-slutartid för tillfället. Kontrollera att kameran är i M-läge."
                )

            # 1. Öppna slutaren
            release_widget.set_value("Press Full")
            cam.set_config(config)

            # 2. Håll slutaren öppen under vald exponeringstid
            time.sleep(req.seconds)

            # 3. Stäng slutaren
            config = cam.get_config()
            release_widget = config.get_child_by_name("eosremoterelease")
            release_widget.set_value("Release Full")
            cam.set_config(config)

            # Vänta kort så kameran hinner skriva klart filen till buffert/SD-kort
            time.sleep(1.0)

            # Ladda ner den senast tagna bilden från kamerans minne
            event_type, event_data = cam.wait_for_event(2000)
            target_url = None
            preview_url = None

            if event_type == gp.GP_EVENT_FILE_ADDED:
                target_file = f"captures/{event_data.name}"
                camera_file = cam.file_get(
                    event_data.folder, event_data.name, gp.GP_FILE_TYPE_NORMAL
                )
                camera_file.save(target_file)
                target_url = f"/captures/{event_data.name}"
                preview_url = target_url

                # Om det är en RAW-fil, ladda ner förhandsvisningen som JPEG
                if event_data.name.lower().endswith((".cr2", ".cr3", ".nef", ".arw", ".dng")):
                    try:
                        preview_file = cam.file_get(
                            event_data.folder, event_data.name, gp.GP_FILE_TYPE_PREVIEW
                        )
                        preview_name = os.path.splitext(event_data.name)[0] + "_preview.jpg"
                        preview_file.save(f"captures/{preview_name}")
                        preview_url = f"/captures/{preview_name}"
                    except Exception as ex:
                        print(f"Kunde inte hämta förhandsvisningsbild för bulb: {ex}")

            # Återställ slutartid
            if bulb_val and original_shutterspeed:
                try:
                    config = cam.get_config()
                    shutterspeed_widget = config.get_child_by_name("shutterspeed")
                    shutterspeed_widget.set_value(original_shutterspeed)
                    cam.set_config(config)
                except Exception as e:
                    print(f"Kunde inte återställa slutartid: {e}")

            return {
                "status": "success",
                "seconds": req.seconds,
                "url": target_url,
                "preview_url": preview_url
            }
        except Exception as e:
            global camera
            camera = None
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@app.get("/api/captures")
def list_captures():
    try:
        files = []
        if os.path.exists("captures"):
            for f in os.listdir("captures"):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".cr2", ".cr3", ".nef", ".arw", ".dng")):
                    if "_preview.jpg" in f:
                        continue

                    preview_url = f"/captures/{f}"
                    if f.lower().endswith((".cr2", ".cr3", ".nef", ".arw", ".dng")):
                        preview_name = os.path.splitext(f)[0] + "_preview.jpg"
                        if os.path.exists(os.path.join("captures", preview_name)):
                            preview_url = f"/captures/{preview_name}"

                    files.append({
                        "filename": f,
                        "url": f"/captures/{f}",
                        "preview_url": preview_url
                    })
            files.sort(key=lambda x: os.path.getmtime(os.path.join("captures", x["filename"])), reverse=True)
        return files
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")