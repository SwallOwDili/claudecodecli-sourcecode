use std::ffi::c_void;
use std::ptr;
use std::sync::Once;
use std::time::Duration;

use napi_derive::napi;
use once_cell::sync::Lazy;
use tokio::sync::broadcast;

type OSStatus = i32;
type AEEventClass = u32;
type AEEventID = u32;
type AEKeyword = u32;
type DescType = u32;
type Size = isize;

#[repr(C)]
struct AEDesc {
    descriptor_type: DescType,
    data_handle: *mut c_void,
}

type AppleEvent = AEDesc;
type AEEventHandler = extern "C" fn(*const AppleEvent, *mut AppleEvent, *mut c_void) -> OSStatus;

#[link(name = "ApplicationServices", kind = "framework")]
extern "C" {
    fn AEInstallEventHandler(
        event_class: AEEventClass,
        event_id: AEEventID,
        handler: AEEventHandler,
        refcon: *mut c_void,
        is_sys_handler: bool,
    ) -> OSStatus;
    fn AEGetParamPtr(
        event: *const AppleEvent,
        keyword: AEKeyword,
        desired_type: DescType,
        actual_type: *mut DescType,
        data: *mut c_void,
        maximum_size: Size,
        actual_size: *mut Size,
    ) -> OSStatus;
}

const fn fourcc(value: &[u8; 4]) -> u32 {
    ((value[0] as u32) << 24)
        | ((value[1] as u32) << 16)
        | ((value[2] as u32) << 8)
        | value[3] as u32
}

const GURL: u32 = fourcc(b"GURL");
const KEY_DIRECT_OBJECT: u32 = fourcc(b"----");
const TYPE_UTF8_TEXT: u32 = fourcc(b"utf8");

static INSTALL: Once = Once::new();
static EVENTS: Lazy<broadcast::Sender<String>> = Lazy::new(|| broadcast::channel(16).0);

extern "C" fn handle_url_event(
    event: *const AppleEvent,
    _reply: *mut AppleEvent,
    _refcon: *mut c_void,
) -> OSStatus {
    let mut buffer = vec![0_u8; 16 * 1024];
    let mut actual_type = 0;
    let mut actual_size = 0;
    let status = unsafe {
        AEGetParamPtr(
            event,
            KEY_DIRECT_OBJECT,
            TYPE_UTF8_TEXT,
            &mut actual_type,
            buffer.as_mut_ptr().cast(),
            buffer.len() as Size,
            &mut actual_size,
        )
    };
    if status == 0 && actual_size > 0 {
        buffer.truncate(actual_size as usize);
        if let Ok(url) = String::from_utf8(buffer) {
            let _ = EVENTS.send(url);
        }
    }
    status
}

fn install_handler() {
    INSTALL.call_once(|| unsafe {
        let _ = AEInstallEventHandler(GURL, GURL, handle_url_event, ptr::null_mut(), false);
    });
}

#[napi]
pub async fn wait_for_url_event(timeout_ms: u32) -> Option<String> {
    install_handler();
    let mut receiver = EVENTS.subscribe();
    tokio::time::timeout(Duration::from_millis(timeout_ms as u64), receiver.recv())
        .await
        .ok()
        .and_then(Result::ok)
}
