# Canon EOS Pro Remote Controller

A modern, mobile-friendly web interface for remote controlling Canon EOS cameras (like the Canon 80D) via USB using a Raspberry Pi or other Linux/Windows servers. Built with **FastAPI** (Python) and **gphoto2**.

## Features

- **Real-Time Live View:** Stream your camera's viewfinder (sökare) directly to your browser with an interactive HUD overlay.
- **Camera Configuration:** View and change settings dynamically (ISO, Shutterspeed, Aperture, White Balance, Image Format).
- **Standard Exposure:** Trigger standard photos and download them directly to your device.
- **Bulb Mode (Long Exposure):** Trigger custom time-controlled exposures (ideal for astrophotography or night shoots).
- **RAW Preview Support:** Automatically extracts and displays the embedded JPEG preview from Canon RAW files (`.CR2`) in the browser.
- **Image Gallery:** Scrollable thumbnail gallery displaying all previous captures, with full-size download support.
- **Mobile Responsive:** Optimized layout using modern CSS grid/flexbox, fitting perfectly on mobile screens (portrait & landscape).

## Prerequisites

The project depends on `libgphoto2`. Make sure you have it installed on your system.

### On Raspberry Pi / Linux:
```bash
sudo apt-get update
sudo apt-get install gphoto2 libgphoto2-dev
```

### Python Dependencies:
```bash
pip install fastapi uvicorn python-gphoto2 anyio pydantic
```

## Running the Application

1. Connect your Canon camera to the server/Raspberry Pi using a USB cable.
2. Turn the camera on and set the physical mode dial to **M (Manual)**.
3. Run the FastAPI server:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```
4. Open your web browser and navigate to `http://<your-ip>:8000`.

## Troubleshooting

### "Device or resource busy" (Linux/Raspberry Pi)
If gphoto2 fails to connect to the camera, it is often because the OS automatically mounted it. Disable the volume monitor using:
```bash
killall gvfs-gphoto2-volume-monitor
```

### Live View does not start
Make sure the camera lens is set to Manual Focus (MF) if it struggles to focus, as auto-focus timeouts can block gphoto2 commands.
