use actix_web::{post, web, HttpRequest, HttpResponse, Responder};
use media_remote::prelude::*;
use std::process::Command;

#[post("/media/play-pause")]
pub async fn play_pause(_req: HttpRequest) -> impl Responder {
    let now_playing = NowPlaying::new();
    if now_playing.toggle() {
        HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
    } else {
        HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": "Failed to toggle play/pause"}))
    }
}

#[post("/media/previous")]
pub async fn previous_track(_req: HttpRequest) -> impl Responder {
    let now_playing = NowPlaying::new();
    if now_playing.previous() {
        HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
    } else {
        HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": "Failed to go to previous track"}))
    }
}

#[post("/media/next")]
pub async fn next_track(_req: HttpRequest) -> impl Responder {
    let now_playing = NowPlaying::new();
    if now_playing.next() {
        HttpResponse::Ok().json(serde_json::json!({"status": "success"}))
    } else {
        HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": "Failed to go to next track"}))
    }
}

#[post("/media/volume-up")]
pub async fn volume_up(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("set volume output volume ((output volume of (get volume settings)) + 10)")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/volume-down")]
pub async fn volume_down(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("set volume output volume ((output volume of (get volume settings)) - 10)")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/volume-set")]
pub async fn set_volume(level: web::Json<i32>, _req: HttpRequest) -> impl Responder {
    let level = level.into_inner().max(0).min(100);
    let result = Command::new("osascript")
        .arg("-e")
        .arg(format!("set volume output volume {}", level))
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/mute")]
pub async fn toggle_mute(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("set volume output muted not (output muted of (get volume settings))")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/up")]
pub async fn arrow_up(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to key code 126")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/down")]
pub async fn arrow_down(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to key code 125")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/left")]
pub async fn arrow_left(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to key code 123")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

#[post("/media/right")]
pub async fn arrow_right(_req: HttpRequest) -> impl Responder {
    let result = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to key code 124")
        .output();
    match result {
        Ok(_) => HttpResponse::Ok().json(serde_json::json!({"status": "success"})),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"status": "error", "error": format!("{:?}", e)})),
    }
}

pub fn init_routes(cfg: &mut web::ServiceConfig) {
    cfg.service(play_pause)
       .service(previous_track)
       .service(next_track)
       .service(volume_up)
       .service(volume_down)
       .service(set_volume)
       .service(toggle_mute)
       .service(arrow_up)
       .service(arrow_down)
       .service(arrow_left)
       .service(arrow_right);
}
