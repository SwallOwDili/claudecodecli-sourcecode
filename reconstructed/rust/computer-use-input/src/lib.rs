use enigo::{Axis, Button, Coordinate, Direction, Enigo, Key, Keyboard, Mouse, Settings};
use napi::bindgen_prelude::*;
use napi_derive::napi;
use objc2_app_kit::NSWorkspace;

#[napi(object)]
pub struct MouseLocation {
    pub x: i32,
    pub y: i32,
}

#[napi(object)]
pub struct FrontmostAppInfo {
    #[napi(js_name = "appName")]
    pub app_name: String,
    #[napi(js_name = "bundleId")]
    pub bundle_id: String,
}

fn enigo() -> Result<Enigo> {
    Enigo::new(&Settings::default()).map_err(|error| {
        Error::from_reason(format!(
            "Error creating Enigo instance: {error:?}\n\nOn macOS, you need to grant accessibility permissions to the terminal or application running this code.\nGo to System Preferences > Security & Privacy > Privacy > Accessibility and add the application."
        ))
    })
}

fn direction(value: &str) -> Result<Direction> {
    match value.to_ascii_lowercase().as_str() {
        "press" => Ok(Direction::Press),
        "release" => Ok(Direction::Release),
        "click" => Ok(Direction::Click),
        _ => Err(Error::from_reason(format!(
            "Invalid action: {value}. Valid options are: press, release, click"
        ))),
    }
}

fn button(value: &str) -> Result<Button> {
    match value.to_ascii_lowercase().as_str() {
        "left" => Ok(Button::Left),
        "right" => Ok(Button::Right),
        "middle" => Ok(Button::Middle),
        "scrollup" => Ok(Button::ScrollUp),
        "scrolldown" => Ok(Button::ScrollDown),
        "scrollleft" => Ok(Button::ScrollLeft),
        "scrollright" => Ok(Button::ScrollRight),
        _ => Err(Error::from_reason(format!(
            "Invalid button name: {value}. Valid options are: left, right, middle, scrollUp, scrollDown, scrollLeft, scrollRight"
        ))),
    }
}

#[allow(deprecated)]
fn key_value(value: &str) -> Result<Key> {
    let normalized = value.to_ascii_lowercase();
    let mapped = match normalized.as_str() {
        "alt" | "option" => Key::Alt,
        "backspace" => Key::Backspace,
        "capslock" => Key::CapsLock,
        "command" | "cmd" | "meta" | "super" => Key::Meta,
        "control" | "ctrl" => Key::Control,
        "delete" => Key::Delete,
        "down" | "downarrow" => Key::DownArrow,
        "end" => Key::End,
        "escape" | "esc" => Key::Escape,
        "home" => Key::Home,
        "left" | "leftarrow" => Key::LeftArrow,
        "pagedown" => Key::PageDown,
        "pageup" => Key::PageUp,
        "return" | "enter" => Key::Return,
        "right" | "rightarrow" => Key::RightArrow,
        "shift" => Key::Shift,
        "space" => Key::Space,
        "tab" => Key::Tab,
        "up" | "uparrow" => Key::UpArrow,
        "f1" => Key::F1,
        "f2" => Key::F2,
        "f3" => Key::F3,
        "f4" => Key::F4,
        "f5" => Key::F5,
        "f6" => Key::F6,
        "f7" => Key::F7,
        "f8" => Key::F8,
        "f9" => Key::F9,
        "f10" => Key::F10,
        "f11" => Key::F11,
        "f12" => Key::F12,
        "f13" => Key::F13,
        "f14" => Key::F14,
        "f15" => Key::F15,
        "f16" => Key::F16,
        "f17" => Key::F17,
        "f18" => Key::F18,
        "f19" => Key::F19,
        "f20" => Key::F20,
        "fn" | "function" => Key::Function,
        "leftcontrol" | "lcontrol" | "leftctrl" | "lctrl" => Key::LControl,
        "rightcontrol" | "rcontrol" | "rightctrl" | "rctrl" => Key::RControl,
        "leftshift" | "lshift" => Key::LShift,
        "rightshift" | "rshift" => Key::RShift,
        "leftoption" | "loption" => Key::Option,
        "rightoption" | "roption" => Key::ROption,
        "rightcommand" | "rcommand" => Key::RCommand,
        "brightnessdown" => Key::BrightnessDown,
        "brightnessup" => Key::BrightnessUp,
        "contrastdown" => Key::ContrastDown,
        "contrastup" => Key::ContrastUp,
        "eject" => Key::Eject,
        "illuminationdown" => Key::IlluminationDown,
        "illuminationup" => Key::IlluminationUp,
        "illuminationtoggle" => Key::IlluminationToggle,
        "launchpad" => Key::Launchpad,
        "launchpanel" => Key::LaunchPanel,
        "missioncontrol" => Key::MissionControl,
        "medianext" | "medianexttrack" => Key::MediaNextTrack,
        "mediaplaypause" => Key::MediaPlayPause,
        "mediaprevious" | "mediaprevtrack" => Key::MediaPrevTrack,
        "mediafast" => Key::MediaFast,
        "mediarewind" => Key::MediaRewind,
        "power" => Key::Power,
        "volumedown" => Key::VolumeDown,
        "volumemute" | "mute" => Key::VolumeMute,
        "volumeup" => Key::VolumeUp,
        "vidmirror" => Key::VidMirror,
        "windows" => Key::Windows,
        "numpad0" => Key::Numpad0,
        "numpad1" => Key::Numpad1,
        "numpad2" => Key::Numpad2,
        "numpad3" => Key::Numpad3,
        "numpad4" => Key::Numpad4,
        "numpad5" => Key::Numpad5,
        "numpad6" => Key::Numpad6,
        "numpad7" => Key::Numpad7,
        "numpad8" => Key::Numpad8,
        "numpad9" => Key::Numpad9,
        "add" => Key::Add,
        "decimal" => Key::Decimal,
        "divide" => Key::Divide,
        "multiply" => Key::Multiply,
        "subtract" => Key::Subtract,
        _ => {
            let mut chars = value.chars();
            match (chars.next(), chars.next()) {
                (Some(character), None) => Key::Unicode(character),
                _ => {
                    return Err(Error::from_reason(format!(
                        "Invalid key name: {value}. Please use a valid key name."
                    )))
                }
            }
        }
    };
    Ok(mapped)
}

#[napi]
pub async fn key(key: String, action: String) -> Result<()> {
    let key = key_value(&key)?;
    let action = direction(&action)?;
    enigo()?
        .key(key, action)
        .map_err(|error| Error::from_reason(format!("Error performing key action: {error}")))
}

#[napi]
pub async fn keys(keys: Vec<String>) -> Result<()> {
    if keys.is_empty() {
        return Err(Error::from_reason("No keys provided"));
    }
    let mut enigo = enigo()?;
    let mut pressed = Vec::new();
    for value in &keys {
        let key = key_value(value)?;
        enigo
            .key(key, Direction::Press)
            .map_err(|error| Error::from_reason(format!("Error pressing key: {error}")))?;
        pressed.push(key);
    }
    for key in pressed.into_iter().rev() {
        enigo
            .key(key, Direction::Release)
            .map_err(|error| Error::from_reason(format!("Error releasing key: {error}")))?;
    }
    Ok(())
}

#[napi]
pub async fn type_text(text: String) -> Result<()> {
    enigo()?
        .text(&text)
        .map_err(|error| Error::from_reason(format!("Error typing text: {error}")))
}

#[napi]
pub async fn move_mouse(x: i32, y: i32, _animate: Option<bool>) -> Result<()> {
    enigo()?
        .move_mouse(x, y, Coordinate::Abs)
        .map_err(|error| Error::from_reason(format!("Error moving mouse: {error}")))
}

#[napi]
pub async fn mouse_button(button_name: String, action: String, count: Option<u32>) -> Result<()> {
    let mut enigo = enigo()?;
    let button = button(&button_name)?;
    let action = direction(&action)?;
    for _ in 0..count.unwrap_or(1).max(1) {
        enigo.button(button, action).map_err(|error| {
            Error::from_reason(format!("Error performing mouse action: {error}"))
        })?;
    }
    Ok(())
}

#[napi]
pub async fn mouse_scroll(length: i32, axis: String) -> Result<()> {
    let mut enigo = enigo()?;
    let axis = match axis.to_ascii_lowercase().as_str() {
        "vertical" => Axis::Vertical,
        "horizontal" => Axis::Horizontal,
        _ => {
            return Err(Error::from_reason(format!(
                "Invalid axis: {axis}. Valid options are: horizontal, vertical"
            )))
        }
    };
    enigo
        .scroll(length, axis)
        .map_err(|error| Error::from_reason(format!("Error performing scroll action: {error}")))
}

#[napi]
pub async fn mouse_location() -> Result<MouseLocation> {
    let (x, y) = enigo()?
        .location()
        .map_err(|error| Error::from_reason(format!("Error getting mouse location: {error}")))?;
    Ok(MouseLocation { x, y })
}

#[napi]
pub fn get_frontmost_app_info() -> Option<FrontmostAppInfo> {
    let application = NSWorkspace::sharedWorkspace().frontmostApplication()?;
    let app_name = application.localizedName()?.to_string();
    let bundle_id = application.bundleIdentifier()?.to_string();
    Some(FrontmostAppInfo {
        app_name,
        bundle_id,
    })
}
