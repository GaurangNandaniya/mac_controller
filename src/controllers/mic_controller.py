import pyaudio
from flask import request
from ..utils import setup_logger
from src.utils.auth_manager import auth_manager
from config import AUDIO_SAMPLE_RATE, AUDIO_CHUNK_SIZE

logger = setup_logger()

# The built-in mic is mono; capture 1 channel so the client decodes it directly.
MIC_CHANNELS = 1


def register_mic_ws(sock):
    """Register /media/mic_ws — streams the Mac's built-in microphone to the client.

    This is the Mac's *input* (what the room/mic hears), distinct from the BlackHole
    system-audio server on 9092 (what the Mac plays). It lives on the main server so
    it inherits TLS + auth: a browser WebSocket can't set an Authorization header, so
    the permanent JWT is passed via ?token= (same pattern as mouse_ws). Blasts raw
    Int16 PCM frames; the client schedules them through Web Audio.
    """

    @sock.route("/media/mic_ws")
    def mic_ws(ws):
        token = request.args.get("token", "")
        _, err = auth_manager.validate_permanent_token(token)
        if err:
            logger.info(f"mic_ws rejected: {err}")
            return  # closes the socket

        p = pyaudio.PyAudio()
        stream = None
        try:
            # Default input device = the built-in mic (unless the user re-routed input).
            try:
                default_in = p.get_default_input_device_info()
                device_index = default_in.get("index")
                logger.info(
                    f"mic_ws: capturing default input '{default_in.get('name')}' (index {device_index})"
                )
            except Exception:
                device_index = None
                logger.warning("mic_ws: no default input device found; using PyAudio default")

            stream = p.open(
                format=pyaudio.paInt16,
                channels=MIC_CHANNELS,
                rate=AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK_SIZE,
                input_device_index=device_index,
            )
            logger.info("mic_ws connected — streaming built-in mic")

            while True:
                # exception_on_overflow=False drops chunks if the CPU falls behind
                # rather than crashing the stream.
                data = stream.read(AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                ws.send(data)

        except Exception as e:
            logger.info(f"mic_ws disconnected or errored: {e}")
        finally:
            if stream is not None and stream.is_active():
                stream.stop_stream()
                stream.close()
            p.terminate()
            logger.info("mic_ws stream closed")
