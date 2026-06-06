import logging
import os
import sys
import pyaudio
from flask import Flask
from flask_sock import Sock
from flask_cors import CORS

# Import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AUDIO_SHARE_PORT, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_CHUNK_SIZE

logger = logging.getLogger('audio_server')

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Minimal standalone player for "Audio Only" mode — open http://<ip>:9092 and tap.
# Tap-to-start is required because browsers keep an AudioContext suspended until a
# user gesture (autoplay policy). Plain string (not f-string) so JS/CSS braces are literal.
AUDIO_ONLY_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>MacPyCtrl Audio</title>
<style>
  html,body{margin:0;height:100%;background:#0b0b0f;color:#eee;font-family:-apple-system,system-ui,sans-serif}
  #wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;text-align:center}
  #icon{font-size:64px}
  #status{font-size:15px;color:#8a8a92}
  #status.live{color:#30d158}
  .bars{display:flex;gap:5px;height:42px;align-items:flex-end}
  .bars span{width:6px;background:#30d158;border-radius:3px;animation:b 1s infinite ease-in-out}
  .bars span:nth-child(2){animation-delay:.15s}.bars span:nth-child(3){animation-delay:.3s}
  .bars span:nth-child(4){animation-delay:.45s}.bars span:nth-child(5){animation-delay:.6s}
  @keyframes b{0%,100%{height:8px}50%{height:42px}}
  #wrap.idle .bars span{animation:none;height:8px;background:#444}
  #overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;flex-direction:column;
           align-items:center;justify-content:center;gap:14px;cursor:pointer;z-index:10}
  #overlay .big{font-size:54px}#overlay .txt{font-size:18px}
  .hidden{display:none}
</style></head>
<body>
  <div id="wrap" class="idle">
    <div id="icon">&#128266;</div>
    <div class="bars"><span></span><span></span><span></span><span></span><span></span></div>
    <div id="status">Connecting&hellip;</div>
  </div>
  <div id="overlay"><div class="big">&#128266;</div><div class="txt">Tap to enable audio</div></div>
<script>
  const statusEl=document.getElementById('status'),wrap=document.getElementById('wrap'),overlay=document.getElementById('overlay');
  let audioCtx=null,ws=null,nextPlayTime=0,started=false;
  function ensureAudio(){if(!audioCtx)audioCtx=new (window.AudioContext||window.webkitAudioContext)();if(audioCtx.state==='suspended')audioCtx.resume();}
  function startOnGesture(){ensureAudio();started=true;overlay.classList.add('hidden');}
  overlay.addEventListener('click',startOnGesture);
  document.addEventListener('touchstart',startOnGesture);
  document.addEventListener('keydown',startOnGesture);
  function connect(){
    const proto=location.protocol==='https:'?'wss:':'ws:';
    ws=new WebSocket(proto+'//'+location.host+'/audio_ws');
    ws.binaryType='arraybuffer';
    ws.onopen=()=>{statusEl.textContent=started?'Live':'Connected \\u2014 tap to listen';};
    ws.onclose=()=>{statusEl.textContent='Disconnected \\u2014 retrying\\u2026';statusEl.classList.remove('live');wrap.classList.add('idle');setTimeout(connect,1000);};
    ws.onerror=()=>ws.close();
    ws.onmessage=(e)=>{
      if(!started)return;                       // wait for the tap; don't buffer pre-gesture audio
      ensureAudio();
      statusEl.textContent='Live';statusEl.classList.add('live');wrap.classList.remove('idle');
      const pcm=new Int16Array(e.data),frames=pcm.length/2;
      const buf=audioCtx.createBuffer(2,frames,48000),L=buf.getChannelData(0),R=buf.getChannelData(1);
      for(let i=0;i<frames;i++){L[i]=pcm[i*2]/32768;R[i]=pcm[i*2+1]/32768;}
      const src=audioCtx.createBufferSource();src.buffer=buf;src.connect(audioCtx.destination);
      const MAX_LATENCY=0.25;
      if(nextPlayTime>audioCtx.currentTime+MAX_LATENCY)nextPlayTime=audioCtx.currentTime+0.05;
      else if(nextPlayTime<audioCtx.currentTime)nextPlayTime=audioCtx.currentTime+0.05;
      src.start(nextPlayTime);nextPlayTime+=buf.duration;
    };
  }
  connect();
</script>
</body></html>"""


@app.route('/')
def index():
    """Standalone audio-only player page."""
    return AUDIO_ONLY_PAGE

def get_blackhole_device_index(p):
    """Finds the PyAudio device index for BlackHole."""
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        if "BlackHole" in dev_info.get("name", "") and dev_info.get("maxInputChannels") > 0:
            return i
    return None

@sock.route('/audio_ws')
def audio_stream(ws):
    """WebSocket endpoint that continuously blasts Int16 PCM arrays to the browser."""
    p = pyaudio.PyAudio()
    device_index = get_blackhole_device_index(p)
    
    if device_index is None:
        logger.warning("BlackHole virtual audio driver not found. Falling back to default input (Microphone).")
        # If BlackHole isn't installed, it will just pick up the MacBook microphone as a fallback.
        
    try:
        stream = p.open(
            format=pyaudio.paInt16, # Int16 provides the most stable backend mapping for BlackHole
            channels=AUDIO_CHANNELS,
            rate=AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=AUDIO_CHUNK_SIZE,
            input_device_index=device_index
        )
        logger.info(f"Audio WS Client Connected. Streaming Int16 from device index {device_index}...")

        while True:
            # Read raw bytes of Int16 PCM buffer
            # exception_on_overflow=False guarantees it drops chunks if CPU gets behind rather than crashing
            data = stream.read(AUDIO_CHUNK_SIZE, exception_on_overflow=False)
            ws.send(data)
            
    except Exception as e:
        logger.info(f"Audio WS client disconnected or errored: {e}")
    finally:
        if 'stream' in locals() and stream.is_active():
            stream.stop_stream()
            stream.close()
        p.terminate()

def run_audio_server():
    """Entry point for the dedicated audio server process."""
    logger.info(f"Starting Dedicated Audio WebSocket Server on port {AUDIO_SHARE_PORT}")
    app.run(
        host='0.0.0.0',
        port=AUDIO_SHARE_PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )

if __name__ == '__main__':
    run_audio_server()
