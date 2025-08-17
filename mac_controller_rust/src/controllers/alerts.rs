#[post("/alerts/stream/audio/v2")]
pub async fn handle_audio_stream_cpal(req: HttpRequest, mut body: web::Payload) -> impl Responder {
    // Get sample rate and channels from headers
    let sample_rate = req.headers().get("X-Sample-Rate")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u32>().ok())
        .unwrap_or(44100);
    let channels = req.headers().get("X-Channels")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(1);

    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
    use std::sync::{Arc, Mutex};
    use tokio::sync::mpsc;

    let host = cpal::default_host();
    let device = match host.default_output_device() {
        Some(d) => d,
        None => {
            return HttpResponse::InternalServerError().json(serde_json::json!({
                "error": "No output device available"
            }));
        }
    };
    let mut supported_configs_range = match device.supported_output_configs() {
        Ok(range) => range,
        Err(e) => {
            return HttpResponse::InternalServerError().json(serde_json::json!({
                "error": format!("Error while querying configs: {}", e)
            }));
        }
    };
    let supported_config = supported_configs_range
        .find(|c| c.channels() == channels && c.min_sample_rate().0 <= sample_rate && c.max_sample_rate().0 >= sample_rate);
    let config = match supported_config {
        Some(cfg) => cfg.with_sample_rate(cpal::SampleRate(sample_rate)),
        None => {
            let fallback = supported_configs_range.next();
            if let Some(fallback) = fallback {
                eprintln!("Warning: No exact config for {}Hz, {}ch. Using fallback: {}Hz, {}ch", sample_rate, channels, fallback.min_sample_rate().0, fallback.channels());
                fallback.with_sample_rate(fallback.min_sample_rate())
            } else {
                return HttpResponse::InternalServerError().json(serde_json::json!({
                    "error": format!("No supported config for {}Hz, {}ch", sample_rate, channels)
                }));
            }
        }
    };

    // Create a channel for streaming audio samples
    let (tx, mut rx) = mpsc::channel::<Vec<i16>>(64); // Increased buffer size
    let output_channels = config.channels();
    let actual_sample_rate = config.sample_rate().0;
    let actual_channels = config.channels();
    let tx_clone = tx.clone();

    // Spawn a thread for audio playback
    std::thread::spawn(move || {
        println!("Audio thread: started");
        let sample_buffer: Vec<i16> = Vec::new();
        let sample_buffer = Arc::new(Mutex::new(sample_buffer));
        let sample_buffer_clone = Arc::clone(&sample_buffer);
        let mut finished = false;
        let stream = match device.build_output_stream(
            &config.config(),
            move |data: &mut [i16], _: &cpal::OutputCallbackInfo| {
                let mut buf = sample_buffer_clone.lock().unwrap();
                let mut idx = 0;
                println!("CPAL callback: buffer size before = {}", buf.len());
                if channels == 1 && output_channels == 2 {
                    for out in data.chunks_mut(2) {
                        let sample = if idx < buf.len() { buf[idx] } else { 0 };
                        out[0] = sample;
                        out[1] = sample;
                        idx += 1;
                    }
                } else {
                    for out in data.iter_mut() {
                        if idx < buf.len() {
                            *out = buf[idx];
                            idx += 1;
                        } else {
                            *out = 0;
                        }
                    }
                }
                println!("CPAL callback: played {} samples, buffer size after = {}", idx, buf.len().saturating_sub(idx));
                // Remove played samples
                buf.drain(0..idx);
            },
            move |err| {
                eprintln!("CPAL stream error: {:?}", err);
            },
            None
        ) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Audio thread: Failed to build output stream: {:?}", e);
                return;
            }
        };
        if let Err(e) = stream.play() {
            eprintln!("Audio thread: Failed to play stream: {:?}", e);
            return;
        }

        // Continuously receive samples from channel
        while !finished {
            if let Some(chunk) = rx.blocking_recv() {
                println!("Audio thread: received chunk of {} samples", chunk.len());
                let mut buf = sample_buffer.lock().unwrap();
                buf.extend(chunk);
                println!("Audio thread: buffer size now {}", buf.len());
            } else {
                finished = true;
            }
        }
        // Wait for buffer to finish playing
        println!("Audio thread: channel closed, waiting for buffer to drain");
        std::thread::sleep(std::time::Duration::from_secs(2));
    });

    // Read body as stream and send samples to channel
    while let Some(Ok(bytes)) = body.next().await {
        let mut samples = Vec::new();
        for chunk in bytes.chunks(2) {
            if chunk.len() == 2 {
                samples.push(i16::from_le_bytes([chunk[0], chunk[1]]));
            } else if chunk.len() == 1 {
                samples.push(i16::from_le_bytes([chunk[0], 0]));
            }
        }
        if tx_clone.send(samples).await.is_err() {
            break;
        }
    }
    // Drop sender to signal end of stream
    drop(tx_clone);

    HttpResponse::Ok().json(serde_json::json!({
        "status": "streaming",
        "requested_sample_rate": sample_rate,
        "requested_channels": channels,
        "actual_sample_rate": actual_sample_rate,
        "actual_channels": actual_channels
    }))
}
use actix_web::{post, web, HttpRequest, HttpResponse, Responder};
// ...existing code...
// ...existing code...
use actix_multipart::Multipart;
use futures_util::stream::StreamExt as _;
use std::fs::File;
use std::io::Write;
use std::path::PathBuf;
use chrono::Local;
use std::process::Command;

#[post("/alerts/upload/audio")]
pub async fn handle_audio_upload(mut payload: Multipart) -> impl Responder {
    // Directory to save audio files
    let upload_dir = dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join("Desktop/intruders/audios");
    if let Err(e) = std::fs::create_dir_all(&upload_dir) {
        return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to create upload dir: {}", e)}));
    }

    // Process multipart payload
    while let Some(item) = payload.next().await {
        match item {
            Ok(mut field) => {
                let filename = field.content_disposition()
                    .and_then(|cd| cd.get_filename())
                    .map(|f| f.to_string())
                    .unwrap_or_else(|| "audio.wav".to_string());
                let timestamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
                let safe_name = filename.replace('/', "_").replace(' ', "_");
                let final_name = format!("{}_{}", timestamp, safe_name);
                let save_path = upload_dir.join(&final_name);

                let mut f = match File::create(&save_path) {
                    Ok(file) => file,
                    Err(e) => {
                        return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to create file: {}", e)}));
                    }
                };

                // Write file contents
                while let Some(chunk) = field.next().await {
                    match chunk {
                        Ok(data) => {
                            if let Err(e) = f.write_all(&data) {
                                return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to write file: {}", e)}));
                            }
                        }
                        Err(e) => {
                            return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to read chunk: {}", e)}));
                        }
                    }
                }


                // Play audio using afplay and log output/errors
                let audio_path = save_path.to_str().unwrap();
                println!("Attempting to play audio: afplay '{}'", audio_path);
                match Command::new("afplay").arg(audio_path).output() {
                    Ok(output) => {
                        if !output.status.success() {
                            println!("afplay failed: status {:?}, stderr: {}", output.status, String::from_utf8_lossy(&output.stderr));
                        } else {
                            println!("afplay succeeded: {}", audio_path);
                        }
                    }
                    Err(e) => {
                        println!("Failed to spawn afplay: {}", e);
                    }
                }

                return HttpResponse::Ok().json(serde_json::json!({
                    "status": "processed",
                    "filename": final_name,
                    "path": save_path.to_str()
                }));
            }
            Err(e) => {
                return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Multipart error: {}", e)}));
            }
        }
    }
    HttpResponse::BadRequest().json(serde_json::json!({"error": "No audio file provided"}))
}

#[post("/alerts/stream/audio")]
pub async fn handle_audio_stream(req: HttpRequest, body: web::Bytes) -> impl Responder {
    // Get sample rate and channels from headers
    let sample_rate = req.headers().get("X-Sample-Rate")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u32>().ok())
        .unwrap_or(44100);
    let channels = req.headers().get("X-Channels")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(1);

    // Save to WAV file
    let upload_dir = dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join("Desktop/intruders/streams");
    if let Err(e) = std::fs::create_dir_all(&upload_dir) {
        return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to create upload dir: {}", e)}));
    }
    let timestamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
    let filename = format!("{}_{}Hz_{}ch.wav", timestamp, sample_rate, channels);
    let save_path = upload_dir.join(&filename);
    let mut wav_file = match File::create(&save_path) {
        Ok(f) => f,
        Err(e) => {
            return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to create file: {}", e)}));
        }
    };
    // Write WAV header and data
    if let Err(e) = write_wav(&mut wav_file, &body, sample_rate, channels) {
        return HttpResponse::InternalServerError().json(serde_json::json!({"error": format!("Failed to write WAV: {}", e)}));
    }

    // Real-time playback using rodio: play the saved WAV file
    use rodio::{OutputStreamBuilder, Sink, Decoder};
    use std::io::BufReader;
    use std::fs::File;
    if let Ok(stream_handle) = OutputStreamBuilder::open_default_stream() {
        let sink = Sink::connect_new(&stream_handle.mixer());
        if let Ok(file) = File::open(&save_path) {
            let reader = BufReader::new(file);
            if let Ok(source) = Decoder::new(reader) {
                sink.append(source);
                sink.sleep_until_end();
            } else {
                println!("Failed to decode WAV file for playback");
            }
        } else {
            println!("Failed to open WAV file for playback");
        }
    } else {
        println!("Failed to create rodio output stream");
    }

    HttpResponse::Ok().json(serde_json::json!({
        "status": "processed",
        "filename": filename,
        "sample_rate": sample_rate,
        "channels": channels
    }))
}

fn write_wav(file: &mut File, data: &[u8], sample_rate: u32, channels: u16) -> std::io::Result<()> {
    use hound::{WavWriter, WavSpec, SampleFormat};
    let spec = WavSpec {
        channels,
        sample_rate,
        bits_per_sample: 16,
        sample_format: SampleFormat::Int,
    };
    let mut writer = WavWriter::new(file, spec).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    for chunk in data.chunks(2) {
        if chunk.len() == 2 {
            let sample = i16::from_le_bytes([chunk[0], chunk[1]]);
            writer.write_sample(sample).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        } else if chunk.len() == 1 {
            // Odd-length data, pad with zero
            let sample = i16::from_le_bytes([chunk[0], 0]);
            writer.write_sample(sample).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        }
    }
    writer.finalize().map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    Ok(())
}

#[post("/alerts/cleanup-audio")]
pub async fn cleanup_audio(_req: HttpRequest) -> impl Responder {
    HttpResponse::Ok().body("cleanup_audio")
}

pub fn init_routes(cfg: &mut web::ServiceConfig) {
    cfg.service(handle_audio_upload)
       .service(handle_audio_stream)
       .service(cleanup_audio);
    cfg.service(handle_audio_stream_cpal);
}
