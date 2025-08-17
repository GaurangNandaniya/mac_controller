use chrono;
use dirs;
use regex;
use actix_web::{web, HttpResponse, Responder};
use serde::Deserialize;
use std::process::Command;
use log::{info, error};

pub fn init_routes(cfg: &mut web::ServiceConfig) {
    cfg
        .service(web::resource("/system/lock").route(web::post().to(lock_screen)))
        .service(web::resource("/system/brightness-up").route(web::post().to(brightness_up)))
        .service(web::resource("/system/brightness-down").route(web::post().to(brightness_down)))
        .service(web::resource("/system/lock").route(web::post().to(sleep_mac)))
        .service(web::resource("/system/battery").route(web::post().to(get_battery)))
        .service(web::resource("/system/keyboard-light-set/{level}").route(web::post().to(set_keyboard_light)))
        .service(web::resource("/system/capture-and-lock").route(web::post().to(capture_and_lock)));
}

async fn lock_screen() -> impl Responder {
    match Command::new("pmset").arg("displaysleepnow").output() {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()})),
    }
}

async fn brightness_up() -> impl Responder {
    let script = "tell application \"System Events\" to Key Code 144";
    match Command::new("osascript").arg("-e").arg(script).output() {
        Ok(_) => {
            info!("Brightness up successful");
            HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
        },
        Err(e) => {
            error!("Error in brightness up: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}))
        }
    }
}
async fn brightness_down() -> impl Responder {
    let script = "tell application \"System Events\" to Key Code 145";
    match Command::new("osascript").arg("-e").arg(script).output() {
        Ok(_) => {
            info!("Brightness down successful");
            HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
        },
        Err(e) => {
            error!("Error in brightness down: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}))
        }
    }
}

async fn sleep_mac() -> impl Responder {
    match Command::new("pmset").arg("sleepnow").output() {
        Ok(_) => {
            info!("System sleep successful");
            HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
        },
        Err(e) => {
            error!("Error in system sleep: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}))
        }
    }
}

async fn get_battery() -> impl Responder {
    match Command::new("pmset").args(["-g", "batt"]).output() {
        Ok(output) => {
            let out_str = String::from_utf8_lossy(&output.stdout);
            let re = regex::Regex::new(r"(\d+)%").unwrap();
            if let Some(cap) = re.captures(&out_str) {
                if let Some(perc) = cap.get(1) {
                    return HttpResponse::Ok().json(serde_json::json!({"status": "success", "percentage": perc.as_str().parse::<u8>().unwrap_or(0)}));
                }
            }
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": "Battery info not found"}))
        },
        Err(e) => {
            error!("Error getting battery percentage: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}))
        }
    }
}

#[derive(Deserialize)]
struct KeyboardLightPath {
    level: u8,
}

async fn set_keyboard_light(path: web::Path<KeyboardLightPath>) -> impl Responder {
    let level = path.level.max(0).min(100);
    // NOTE: Actual macOS keyboard backlight control may require privileged access and custom code.
    // This is a placeholder for the shell command logic.
    let hex_value = format!("{:02x}", ((level as f32 / 100.0) * 255.0) as u8);
    let cmd = format!("ioreg -n AppleHSKeyboardBacklight -r -d 1 | grep -i 'brightness' | awk '{{print $3}}' | sudo ioreg -c AppleHSKeyboardBacklight -w0 -f -r -d 1 | grep -i 'brightness' | awk '{{print $3}}' | xargs -I % sudo ioreg -c AppleHSKeyboardBacklight -w0 -f -r -d 1 -w {}", hex_value);
    match Command::new("sh").arg("-c").arg(&cmd).output() {
        Ok(_) => {
            info!("Keyboard brightness set to {}% successful", level);
            HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
        },
        Err(e) => {
            error!("Error setting keyboard brightness to {}%: {}", level, e);
            HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}))
        }
    }
}

async fn capture_and_lock() -> impl Responder {
    use chrono::Local;
    use std::fs;
    use std::path::PathBuf;

    let timestamp = Local::now().format("%Y-%m-%d_%H-%M-%S").to_string();
    let base_path = dirs::home_dir().unwrap_or_else(|| PathBuf::from("/tmp")).join("Desktop/intruders");
    let session_path = base_path.join(format!("session_{}", timestamp));
    if let Err(e) = fs::create_dir_all(&session_path) {
        error!("Failed to create session directory: {}", e);
        return HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}));
    }

    // 1. Capture Screen
    let screenshot_path = session_path.join("screenshot.png");
    if let Err(e) = Command::new("screencapture").args(["-x", screenshot_path.to_str().unwrap()]).output() {
        error!("Failed to capture screen: {}", e);
        return HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}));
    }

    // 2. Capture Webcam (requires external tool, e.g., imagesnap)
    let webcam_path = session_path.join("webcam.jpg");
    if let Err(e) = Command::new("imagesnap").arg(webcam_path.to_str().unwrap()).output() {
        error!("Failed to capture webcam: {}", e);
        return HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}));
    }

    // 3. Lock MacBook
    if let Err(e) = Command::new("pmset").arg("displaysleepnow").output() {
        error!("Failed to lock MacBook: {}", e);
        return HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": e.to_string()}));
    }

    info!("Capture and lock successful");
    HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
}
