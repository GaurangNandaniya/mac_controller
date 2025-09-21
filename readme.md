# Mac Controller Server

A dual-implementation server (Python/Flask and Rust/Actix) providing remote control capabilities for your Mac, including media control, system management, and security features.

## Prerequisites

### Python Implementation

- Python 3.x
- macOS operating system
- Virtual environment (recommended)

### Rust Implementation

- Rust 1.65+ toolchain
- Cargo package manager
- macOS operating system

## Application Flow

1. **Startup**:

   ```bash
   python mac_controller_app.py
   ```

   - Creates menu bar icon
   - Auto-starts HTTPS server with certificates from `.env`
   - Registers mDNS service for local discovery

2. **First Run Setup**:

   - Generate certificates using mkcert
     Generate a trusted cert for those names

     Run this in your project folder:

     ```
     mkcert myservice.local 192.168.1.25 localhost 127.0.0.1 ::1
     ```

     You’ll get two files (names may vary slightly):

     ```
     myservice.local+4.pem # certificate
     myservice.local+4-key.pem # private key
     ```

- Configure `.env` file with paths to certificates
- Create Automator app for easy startup

3. **Daily Operation**:
   - Control via menu bar options or web interface
   - Devices authenticate via QR code pairing
   - All communication over encrypted HTTPS

## Installation & Setup

1. Clone the repository:

```bash
git clone https://github.com/GaurangNandaniya/mac_controller.git
cd mac_controller
```

### Companion Web App Setup

The iOS/web interface is available at:
https://github.com/GaurangNandaniya/mac-control-web-app

Key features:

- Progressive Web App (PWA)
- Responsive mobile-first design
- Secure communication with your Mac controller
- Avoids iOS sideloading limitations (7-day expiration bypass) There an ios and watch OS app as well in case interested.

To use:

````bash
git clone https://github.com/GaurangNandaniya/mac-control-web-app.git
cd mac-control-web-app
npm install
npm run build
# Deploy the build folder to your hosting service

### Python Requirements

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
````

### Certificate Setup

1. Install mkcert:

```bash
brew install mkcert nss
mkcert -install
```

2. Generate certificates (run in project root):

```bash
IP=$(ipconfig getifaddr en0)
mkcert $IP mymac.local localhost
# Certificates will be created in current directory
```

3. Configure `.env`:

```ini
CERTIFICATE_PATH=./192.168.x.x+2.pem
PRIVATE_KEY_PATH=./192.168.x.x+2-key.pem
AUTH_SECRET_KEY=your-secure-key-here
MAX_DEVICES=5
WEB_APP_URL=https://your-deployment.com
```

### iPhone Pairing Guide

1. Locate root CA certificate:
   ```bash
   mkcert -CAROOT  # Shows CA certificate location
   ```
2. Transfer `rootCA.pem` to iPhone using:
   - AirDrop
   - Email attachment
   - Cloud storage
3. On iPhone:
   - Open certificate file → Install profile
   - Go to Settings → General → About → Certificate Trust Settings
   - Enable "Full Trust" for mkcert root CA

### Automator & Startup Configuration

1. Make shell script executable:

```bash
chmod +x start_mac_controller_server.sh
```

2. Create Automator App:

   - New Document → Application
   - Add "Run Shell Script" action:

   ```bash
   export macControllerDirPath="/PATH/TO/YOUR/mac_controller"
   /bin/bash "$macControllerDirPath/start_mac_controller_server.sh"
   ```

   - Save as `Mac Controller.app`

3. Enable Auto-Start (Optional):
   - System Settings → General → Login Items
   - Click ➕ and select `Mac Controller.app`
   - Check "Open at Login" option

## Server Management

- **Manual Start**: Run `mac_controller_app.py` directly
- **Auto-Start**: Login Items launch Automator app
- **Menu Options**:
  - 🟢/🔴 Start/Stop Server
  - QR Code Generation
  - Connected Device Management
  - Server Status Monitoring

## Rust Implementation

### Building and Running

1. Navigate to Rust project:

```bash
cd mac_controller_rust
```

2. Build the project:

```bash
cargo build --release
```

3. Run the server:

```bash
cargo run --release
```

The Rust server will:

- Start on port 8080
- Advertise via mDNS as `MacPyCTRLServer`
- Log connection details to consolen

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

- **Python**: Uses Flask development server with mDNS advertising
- **Rust**: Uses Actix-web with Tokio runtime and zeroconf-based mDNS
- Both implementations advertise via mDNS as `MacPyCTRLServer`
- All endpoints return JSON responses with a "status" field
- Error responses include an "error" field with the error message
- Some endpoints require specific permissions (e.g., keyboard control, screen capture)
- Audio files and captures are saved to the Desktop/intruders directory

## Security Considerations

- Applies to both implementations:
  - Should be run in trusted network environments
  - System control endpoints require elevated privileges
  - Audio/file endpoints create persistent storage in ~/Desktop/intruders/
- Rust-specific:
  - Compiled binary reduces attack surface vs interpreted Python
  - Uses Rust's memory safety guarantees for critical system operations
- Consider implementing authentication for production use
- Be cautious with system control endpoints as they can affect your Mac's operation
