import asyncio
import json
import os
import sys
import time

import av
import cv2
import mss
import numpy as np

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay

# Add the parent directory to sys.path so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WEBRTC_SHARE_PORT, WEBRTC_FPS

relay = MediaRelay()
pcs = set()

# A single persistent track if we want to share it among multiple connections.
# For simplicity, we just initialize it per connection right now.

class ScreenStreamTrack(VideoStreamTrack):
    """
    A video stream track that reads from the screen capture using mss.
    Uses asyncio to properly pace the frames for WebRTC encoding.
    """
    def __init__(self, fps):
        super().__init__()
        self.fps = fps
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.logical_w = self.monitor['width']
        self.frame_duration = 1.0 / self.fps

    async def recv(self):
        # next_timestamp() perfectly paces the frame delivery according to RTP clock
        pts, time_base = await self.next_timestamp()

        # Capture using mss (very fast)
        screenshot = self.sct.grab(self.monitor)
        raw = np.array(screenshot)

        # Downscale logic for Retina displays (matches MJPEG downscaler exactly)
        if raw.shape[1] > self.logical_w:
            frame_bgr = raw[::2, ::2, :3]
        else:
            frame_bgr = raw[:, :, :3]

        # Convert simple numpy BGR to av.VideoFrame
        new_frame = av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        
        return new_frame


async def handle_options(request):
    """Handles CORS preflight requests from external web apps hitting the WebRTC endpoint."""
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })

async def offer(request):
    """
    Handles WebRTC SDP negotiation. Receives an offer, creates a connection,
    adds the video track, and returns the SDP answer.
    """
    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"WebRTC Connection state is {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            pcs.discard(pc)

    # Attach the screen streaming track
    track = ScreenStreamTrack(fps=WEBRTC_FPS)
    pc.addTrack(track)

    # Handle the offer and create an answer
    await pc.setRemoteDescription(offer_sdp)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }, headers={
        "Access-Control-Allow-Origin": "*"
    })


async def index(request):
    """Serve the WebRTC HTML viewer file."""
    html_path = os.path.join(os.path.dirname(__file__), 'templates', 'webrtc_share.html')
    with open(html_path, "r") as f:
        content = f.read()
    return web.Response(content_type="text/html", text=content)


async def on_shutdown(app):
    """Clean up active WebRTC connections."""
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


def run_webrtc_server():
    """Entry point for the WebRTC subprocess."""
    print(f"Starting WebRTC Screen Share server on port {WEBRTC_SHARE_PORT}...")
    
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_options("/offer", handle_options)

    # Access log is disabled to maximize frame performance
    web.run_app(app, host="0.0.0.0", port=WEBRTC_SHARE_PORT, access_log=None)


if __name__ == "__main__":
    run_webrtc_server()
