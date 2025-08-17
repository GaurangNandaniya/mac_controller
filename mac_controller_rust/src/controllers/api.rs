use actix_web::{get, web, HttpRequest, HttpResponse, Responder};

#[get("/api/ping")]
pub async fn ping(_req: HttpRequest) -> impl Responder {
    HttpResponse::Ok().body("pong")
}

pub fn init_routes(cfg: &mut web::ServiceConfig) {
    cfg.service(ping);
}
