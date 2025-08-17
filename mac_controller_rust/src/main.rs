use local_ip_address;
use actix_web::{App, HttpServer};
use log::info;
use std::net::Ipv4Addr;
mod mdns_service;

// mod system_controller; // moved to controllers
mod controllers;

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::init();
    info!("Starting mac_controller_rust server...");

    // Get local IP (simple method, can be improved)
    let ip = local_ip_address::local_ip().map(|ip| ip.to_string()).unwrap_or_else(|_| "127.0.0.1".to_string());
    let ip_addr: Ipv4Addr = ip.parse().unwrap_or(Ipv4Addr::LOCALHOST);
    let port = 8080;
    std::thread::spawn(move || {
        let _ = mdns_service::register_mdns_service(port);
    });

    HttpServer::new(|| {
        App::new()
            .configure(controllers::media::init_routes)
            .configure(controllers::system::init_routes)
            .configure(controllers::connections::init_routes)
            .configure(controllers::alerts::init_routes)
            .configure(controllers::api::init_routes)
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
