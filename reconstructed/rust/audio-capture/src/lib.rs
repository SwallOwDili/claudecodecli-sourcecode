use std::collections::VecDeque;
use std::ffi::{c_char, c_void};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream, StreamConfig};
use napi::bindgen_prelude::*;
use napi::threadsafe_function::{ErrorStrategy, ThreadsafeFunction, ThreadsafeFunctionCallMode};
use napi_derive::napi;
use once_cell::sync::Lazy;

const RTLD_LAZY: i32 = 1;

#[link(name = "objc")]
extern "C" {
    fn objc_getClass(name: *const c_char) -> *mut c_void;
    fn sel_registerName(name: *const c_char) -> *mut c_void;
}

extern "C" {
    fn dlopen(path: *const c_char, mode: i32) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
}

const OUTPUT_SAMPLE_RATE: u32 = 16_000;

static AUDIO_RUNTIME: Lazy<AudioRuntime> = Lazy::new(AudioRuntime::spawn);

type DataCallback = ThreadsafeFunction<Buffer, ErrorStrategy::CalleeHandled>;
type SilenceCallback = ThreadsafeFunction<(), ErrorStrategy::CalleeHandled>;

struct AudioRuntime {
    sender: mpsc::Sender<AudioCommand>,
    recording: Arc<AtomicBool>,
    playing: Arc<AtomicBool>,
}

enum AudioCommand {
    StartRecording {
        data_callback: DataCallback,
        silence_callback: SilenceCallback,
        response: mpsc::SyncSender<std::result::Result<bool, String>>,
    },
    StopRecording,
    StartPlayback {
        response: mpsc::SyncSender<std::result::Result<bool, String>>,
    },
    WritePlayback(Vec<u8>),
    StopPlayback,
}

impl AudioRuntime {
    fn spawn() -> Self {
        let (sender, receiver) = mpsc::channel();
        let recording = Arc::new(AtomicBool::new(false));
        let playing = Arc::new(AtomicBool::new(false));
        let recording_for_thread = recording.clone();
        let playing_for_thread = playing.clone();
        thread::Builder::new()
            .name("claude-audio-runtime".to_string())
            .spawn(move || {
                run_audio_thread(receiver, recording_for_thread, playing_for_thread);
            })
            .expect("failed to create Claude audio runtime thread");
        Self {
            sender,
            recording,
            playing,
        }
    }
}

struct PlaybackRuntime {
    _stream: Stream,
    queue: Arc<Mutex<VecDeque<i16>>>,
}

struct CaptureConverter {
    input_rate: u32,
    channels: usize,
    phase: u32,
    silent_samples: usize,
    silence_reported: bool,
}

impl CaptureConverter {
    fn new(config: &StreamConfig) -> Self {
        Self {
            input_rate: config.sample_rate.0,
            channels: config.channels as usize,
            phase: 0,
            silent_samples: 0,
            silence_reported: false,
        }
    }

    fn convert(&mut self, samples: &[f32]) -> (Vec<u8>, bool) {
        let mut output = Vec::new();
        for frame in samples.chunks(self.channels) {
            if frame.is_empty() {
                continue;
            }
            let mono = frame.iter().copied().sum::<f32>() / frame.len() as f32;
            self.phase = self.phase.saturating_add(OUTPUT_SAMPLE_RATE);
            if self.phase < self.input_rate {
                continue;
            }
            self.phase -= self.input_rate;
            let value = (mono.clamp(-1.0, 1.0) * i16::MAX as f32) as i16;
            output.extend_from_slice(&value.to_le_bytes());
            if mono.abs() < 0.03 {
                self.silent_samples += 1;
            } else {
                self.silent_samples = 0;
                self.silence_reported = false;
            }
        }
        let silence =
            !self.silence_reported && self.silent_samples >= OUTPUT_SAMPLE_RATE as usize * 2;
        if silence {
            self.silence_reported = true;
        }
        (output, silence)
    }
}

#[napi]
pub fn is_recording() -> bool {
    AUDIO_RUNTIME.recording.load(Ordering::Acquire)
}

#[napi]
pub fn is_playing() -> bool {
    AUDIO_RUNTIME.playing.load(Ordering::Acquire)
}

#[napi]
pub fn start_recording(on_data: JsFunction, on_silence: JsFunction) -> Result<bool> {
    let data_callback: DataCallback =
        on_data.create_threadsafe_function(0, |context| Ok(vec![context.value]))?;
    let silence_callback: SilenceCallback =
        on_silence.create_threadsafe_function(0, |_context| Ok(Vec::<String>::new()))?;
    let (response, result) = mpsc::sync_channel(1);
    AUDIO_RUNTIME
        .sender
        .send(AudioCommand::StartRecording {
            data_callback,
            silence_callback,
            response,
        })
        .map_err(|_| Error::from_reason("Audio runtime stopped"))?;
    result
        .recv()
        .map_err(|_| Error::from_reason("Audio runtime stopped"))?
        .map_err(Error::from_reason)
}

fn build_recording_stream(
    data_callback: DataCallback,
    silence_callback: SilenceCallback,
) -> std::result::Result<Option<Stream>, String> {
    let host = cpal::default_host();
    let device = match host.default_input_device() {
        Some(device) => device,
        None => return Ok(None),
    };
    let supported = device
        .default_input_config()
        .map_err(|error| format!("Failed to get input configuration: {error}"))?;
    let sample_format = supported.sample_format();
    let config: StreamConfig = supported.into();
    let converter = Arc::new(Mutex::new(CaptureConverter::new(&config)));
    let error_callback = |_error| {};

    let stream = match sample_format {
        SampleFormat::F32 => {
            let converter = converter.clone();
            let data_callback = data_callback.clone();
            let silence_callback = silence_callback.clone();
            device.build_input_stream(
                &config,
                move |data: &[f32], _| {
                    emit_capture(data, &converter, &data_callback, &silence_callback)
                },
                error_callback,
                None,
            )
        }
        SampleFormat::I16 => {
            let converter = converter.clone();
            let data_callback = data_callback.clone();
            let silence_callback = silence_callback.clone();
            device.build_input_stream(
                &config,
                move |data: &[i16], _| {
                    let converted: Vec<f32> = data
                        .iter()
                        .map(|value| *value as f32 / i16::MAX as f32)
                        .collect();
                    emit_capture(&converted, &converter, &data_callback, &silence_callback);
                },
                error_callback,
                None,
            )
        }
        SampleFormat::U16 => {
            let converter = converter.clone();
            let data_callback = data_callback.clone();
            let silence_callback = silence_callback.clone();
            device.build_input_stream(
                &config,
                move |data: &[u16], _| {
                    let converted: Vec<f32> = data
                        .iter()
                        .map(|value| (*value as f32 / u16::MAX as f32) * 2.0 - 1.0)
                        .collect();
                    emit_capture(&converted, &converter, &data_callback, &silence_callback);
                },
                error_callback,
                None,
            )
        }
        _ => return Err("Unsupported input sample format".to_string()),
    }
    .map_err(|error| format!("Failed to build input stream: {error}"))?;
    stream
        .play()
        .map_err(|error| format!("Failed to start input stream: {error}"))?;
    Ok(Some(stream))
}

fn emit_capture(
    samples: &[f32],
    converter: &Arc<Mutex<CaptureConverter>>,
    data_callback: &ThreadsafeFunction<Buffer, ErrorStrategy::CalleeHandled>,
    silence_callback: &ThreadsafeFunction<(), ErrorStrategy::CalleeHandled>,
) {
    let (bytes, silence) = match converter.lock() {
        Ok(mut converter) => converter.convert(samples),
        Err(_) => return,
    };
    if !bytes.is_empty() {
        let _ = data_callback.call(
            Ok(Buffer::from(bytes)),
            ThreadsafeFunctionCallMode::NonBlocking,
        );
    }
    if silence {
        let _ = silence_callback.call(Ok(()), ThreadsafeFunctionCallMode::NonBlocking);
    }
}

#[napi]
pub fn stop_recording() {
    AUDIO_RUNTIME.recording.store(false, Ordering::Release);
    let _ = AUDIO_RUNTIME.sender.send(AudioCommand::StopRecording);
}

#[napi]
pub fn start_playback(_sample_rate: u32, _channels: u16) -> Result<bool> {
    let (response, result) = mpsc::sync_channel(1);
    AUDIO_RUNTIME
        .sender
        .send(AudioCommand::StartPlayback { response })
        .map_err(|_| Error::from_reason("Audio runtime stopped"))?;
    result
        .recv()
        .map_err(|_| Error::from_reason("Audio runtime stopped"))?
        .map_err(Error::from_reason)
}

fn build_playback_stream() -> std::result::Result<Option<PlaybackRuntime>, String> {
    let host = cpal::default_host();
    let device = match host.default_output_device() {
        Some(device) => device,
        None => return Ok(None),
    };
    let supported = device
        .default_output_config()
        .map_err(|error| format!("Failed to get output configuration: {error}"))?;
    let sample_format = supported.sample_format();
    let config: StreamConfig = supported.into();
    let queue = Arc::new(Mutex::new(VecDeque::new()));
    let error_callback = |_error| {};
    let stream = match sample_format {
        SampleFormat::F32 => {
            let queue = queue.clone();
            device.build_output_stream(
                &config,
                move |output: &mut [f32], _| {
                    fill_output(output, &queue, |value| value as f32 / i16::MAX as f32)
                },
                error_callback,
                None,
            )
        }
        SampleFormat::I16 => {
            let queue = queue.clone();
            device.build_output_stream(
                &config,
                move |output: &mut [i16], _| fill_output(output, &queue, |value| value),
                error_callback,
                None,
            )
        }
        SampleFormat::U16 => {
            let queue = queue.clone();
            device.build_output_stream(
                &config,
                move |output: &mut [u16], _| {
                    fill_output(output, &queue, |value| (value as i32 + 32768) as u16)
                },
                error_callback,
                None,
            )
        }
        _ => return Err("Unsupported output sample format".to_string()),
    }
    .map_err(|error| format!("Failed to build output stream: {error}"))?;
    stream
        .play()
        .map_err(|error| format!("Failed to start output stream: {error}"))?;
    Ok(Some(PlaybackRuntime {
        _stream: stream,
        queue,
    }))
}

fn fill_output<T: Copy>(
    output: &mut [T],
    queue: &Arc<Mutex<VecDeque<i16>>>,
    convert: impl Fn(i16) -> T,
) {
    if let Ok(mut queue) = queue.lock() {
        for sample in output {
            *sample = convert(queue.pop_front().unwrap_or(0));
        }
    }
}

#[napi]
pub fn write_playback_data(data: Buffer) {
    let _ = AUDIO_RUNTIME
        .sender
        .send(AudioCommand::WritePlayback(data.as_ref().to_vec()));
}

#[napi]
pub fn stop_playback() {
    AUDIO_RUNTIME.playing.store(false, Ordering::Release);
    let _ = AUDIO_RUNTIME.sender.send(AudioCommand::StopPlayback);
}

#[napi]
pub fn microphone_authorization_status() -> i32 {
    unsafe {
        let av_foundation = dlopen(
            c"/System/Library/Frameworks/AVFoundation.framework/AVFoundation".as_ptr(),
            RTLD_LAZY,
        );
        if av_foundation.is_null() {
            return 0;
        }
        let media_type_symbol = dlsym(av_foundation, c"AVMediaTypeAudio".as_ptr());
        if media_type_symbol.is_null() {
            return 0;
        }
        let media_type = *(media_type_symbol as *const *mut c_void);
        if media_type.is_null() {
            return 0;
        }
        let capture_device = objc_getClass(c"AVCaptureDevice".as_ptr());
        if capture_device.is_null() {
            return 0;
        }
        let selector = sel_registerName(c"authorizationStatusForMediaType:".as_ptr());
        let objc = dlopen(c"/usr/lib/libobjc.A.dylib".as_ptr(), RTLD_LAZY);
        if objc.is_null() {
            return 0;
        }
        let message_send = dlsym(objc, c"objc_msgSend".as_ptr());
        if message_send.is_null() {
            return 0;
        }
        let send: unsafe extern "C" fn(*mut c_void, *mut c_void, *mut c_void) -> isize =
            std::mem::transmute(message_send);
        send(capture_device, selector, media_type) as i32
    }
}

fn run_audio_thread(
    receiver: mpsc::Receiver<AudioCommand>,
    recording_state: Arc<AtomicBool>,
    playing_state: Arc<AtomicBool>,
) {
    let mut recording: Option<Stream> = None;
    let mut playback: Option<PlaybackRuntime> = None;

    while let Ok(command) = receiver.recv() {
        match command {
            AudioCommand::StartRecording {
                data_callback,
                silence_callback,
                response,
            } => {
                recording.take();
                recording_state.store(false, Ordering::Release);
                let result = build_recording_stream(data_callback, silence_callback);
                let reply = match result {
                    Ok(stream) => {
                        let started = stream.is_some();
                        recording = stream;
                        recording_state.store(started, Ordering::Release);
                        Ok(started)
                    }
                    Err(error) => Err(error),
                };
                let _ = response.send(reply);
            }
            AudioCommand::StopRecording => {
                recording.take();
                recording_state.store(false, Ordering::Release);
            }
            AudioCommand::StartPlayback { response } => {
                playback.take();
                playing_state.store(false, Ordering::Release);
                let result = build_playback_stream();
                let reply = match result {
                    Ok(runtime) => {
                        let started = runtime.is_some();
                        playback = runtime;
                        playing_state.store(started, Ordering::Release);
                        Ok(started)
                    }
                    Err(error) => Err(error),
                };
                let _ = response.send(reply);
            }
            AudioCommand::WritePlayback(bytes) => {
                let Some(runtime) = playback.as_ref() else {
                    continue;
                };
                if let Ok(mut queue) = runtime.queue.lock() {
                    for chunk in bytes.chunks_exact(2) {
                        queue.push_back(i16::from_le_bytes([chunk[0], chunk[1]]));
                    }
                }
            }
            AudioCommand::StopPlayback => {
                playback.take();
                playing_state.store(false, Ordering::Release);
            }
        }
    }

    recording_state.store(false, Ordering::Release);
    playing_state.store(false, Ordering::Release);
}
