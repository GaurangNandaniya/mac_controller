use zeroconf::{prelude::*, ServiceRegistration};
use zeroconf::{MdnsService, ServiceType, TxtRecord};
use std::sync::{Arc, Mutex};
use std::task::Context;
use std::time::Duration;
use std::any::Any;
use log::info;

pub fn register_mdns_service(port: u16) -> zeroconf::Result<()> {
    // Service type: "_macpyctrlserver._tcp.local."
    let service_type = ServiceType::new("macpyctrlserver", "tcp")?;
    let mut service = MdnsService::new(service_type, port);

    // Service name: "MacPyCTRLServer._macpyctrlserver._tcp.local."
    service.set_name("MacPyCTRLServer");
    // service.set_registered_callback(Box::new(on_service_registered));

    // TXT record: version=1.0, description=Test server
    let mut txt_record = TxtRecord::new();
    txt_record.insert("version", "1.0")?;
    txt_record.insert("description", "Test server")?;
    service.set_txt_record(txt_record);

    // Register the service
    let event_loop = service.register()?;
    info!("Registered mDNS service!");

    // Keep the service alive
    loop {
        event_loop.poll(Duration::from_secs(1))?;
    }
}


fn on_service_registered(
    result: zeroconf::Result<ServiceRegistration>,
    context: Option<Arc<dyn Any>>,
) {
    let service = result.expect("failed to register service");

    info!("Service registered: {:?}", service);


    info!("Context: {:?}", context);

    // ...
}