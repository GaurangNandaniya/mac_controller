# Mac Controller Server

A Flask-based server that provides remote control capabilities for your Mac, including media control, system management, and security features.

## Prerequisites

- Python 3.x
- macOS operating system
- Virtual environment (recommended)

## Setup Instructions

1. Clone the repository:

```bash
git clone git@github.com:GaurangNandaniya/mac_controller.git
cd mac_controller
```

2. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the server:

```bash
python run.py
```

The server will start and display the local URL and mDNS name for connection.

## API Endpoints

### Media Control

- `POST /media/play-pause`

  - Toggles play/pause for media
  - Response: `{"status": "success"}`

- `POST /media/previous`

  - Plays previous track
  - Response: `{"status": "success"}`

- `POST /media/next`

  - Plays next track
  - Response: `{"status": "success"}`

- `POST /media/volume-up`

  - Increases volume
  - Response: `{"status": "success"}`

- `POST /media/volume-down`

  - Decreases volume
  - Response: `{"status": "success"}`

- `POST /media/volume-set/<int:level>`

  - Sets volume to specific level (0-100)
  - Response: `{"status": "success"}`

- `POST /media/mute`
  - Toggles mute
  - Response: `{"status": "success"}`

### System Control

- `POST /system/lock`

  - Locks the screen
  - Response: `{"status": "success"}`

- `POST /system/brightness-up`

  - Increases screen brightness
  - Response: `{"status": "success"}`

- `POST /system/brightness-down`

  - Decreases screen brightness
  - Response: `{"status": "success"}`

- `POST /system/sleep`

  - Puts the system to sleep
  - Response: `{"status": "success"}`

- `POST /system/battery`

  - Gets battery percentage
  - Response: `{"status": "success", "percentage": <number>}`

- `POST /system/keyboard-light-set/<int:level>`

  - Sets keyboard backlight level (0-100)
  - Response: `{"status": "success"}`

- `POST /system/capture-and-lock`
  - Takes screenshot and webcam photo, then locks the system
  - Saves files to `~/Desktop/intruders/session_<timestamp>/`
  - Response: `{"status": "success"}`

### Alerts

- `POST /alerts/upload/audio`

  - Uploads and plays an audio file
  - Accepts multipart form data with 'audio' file
  - Saves to `~/Desktop/intruders/audios/`
  - Response: `{"status": "processed", "filename": <filename>, "path": <path>}`

- `POST /alerts/stream/audio`
  - Streams real-time audio
  - Headers required:
    - `X-Sample-Rate`: Audio sample rate (default: 44100)
    - `X-Channels`: Number of channels (default: 1)
  - Response: `{"status": "processed", "filename": <filename>, "sample_rate": <rate>, "channels": <channels>}`

### Connections

- `POST /connections/ping`
  - Returns server IP and port if pinged with "MAC_ADDRESS_PING"
  - Response: `<ip>:<port>` or empty string

### General API

- `POST /api/hello`
  - Basic ping endpoint
  - Response: "Hi from mac"

## Notes

- The server uses mDNS for discovery, making it accessible via the hostname `MacPyCTRLServer`
- All endpoints return JSON responses with a "status" field
- Error responses include an "error" field with the error message
- Some endpoints require specific permissions (e.g., keyboard control, screen capture)
- Audio files and captures are saved to the Desktop/intruders directory

## Security Considerations

- The server should be run in a trusted network environment
- Consider implementing authentication for production use
- Be cautious with system control endpoints as they can affect your Mac's operation
