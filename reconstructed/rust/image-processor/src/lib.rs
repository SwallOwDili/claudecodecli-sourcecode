use std::io::Cursor;
use std::sync::{Arc, Mutex};

use arboard::Clipboard;
use image::imageops::FilterType;
use image::{DynamicImage, GenericImageView, ImageFormat};
use napi::bindgen_prelude::*;
use napi_derive::napi;

#[napi(object)]
pub struct ImageMetadata {
    pub width: u32,
    pub height: u32,
    pub format: String,
}

#[napi(object)]
pub struct ResizeOptions {
    pub fit: Option<String>,
    #[napi(js_name = "withoutEnlargement")]
    pub without_enlargement: Option<bool>,
}

#[napi(object)]
pub struct PngOptions {
    pub compression_level: Option<u8>,
}

#[napi(object)]
pub struct ClipboardImage {
    pub png: Buffer,
    #[napi(js_name = "originalWidth")]
    pub original_width: u32,
    #[napi(js_name = "originalHeight")]
    pub original_height: u32,
    pub width: u32,
    pub height: u32,
}

struct ImageState {
    image: DynamicImage,
    source_format: ImageFormat,
    output_format: ImageFormat,
    quality: u8,
}

#[napi]
pub struct ImageProcessor {
    state: Arc<Mutex<Option<ImageState>>>,
}

impl ImageProcessor {
    fn with_state<T>(&self, operation: impl FnOnce(&mut ImageState) -> Result<T>) -> Result<T> {
        let mut guard = self
            .state
            .lock()
            .map_err(|_| Error::from_reason("ImageProcessor lock poisoned"))?;
        let state = guard.as_mut().ok_or_else(|| {
            Error::from_reason("ImageProcessor already consumed (toBuffer/dispose was called)")
        })?;
        operation(state)
    }
}

#[napi]
impl ImageProcessor {
    #[napi]
    pub fn metadata(&self) -> Result<ImageMetadata> {
        self.with_state(|state| {
            let (width, height) = state.image.dimensions();
            Ok(ImageMetadata {
                width,
                height,
                format: format_name(state.source_format).to_string(),
            })
        })
    }

    #[napi]
    pub fn resize(
        &self,
        this: This,
        width: u32,
        height: u32,
        options: Option<ResizeOptions>,
    ) -> Result<This> {
        self.with_state(|state| {
            let (source_width, source_height) = state.image.dimensions();
            let without_enlargement = options
                .as_ref()
                .and_then(|value| value.without_enlargement)
                .unwrap_or(false);
            let (target_width, target_height) = if without_enlargement {
                (width.min(source_width), height.min(source_height))
            } else {
                (width, height)
            };
            let fit = options
                .as_ref()
                .and_then(|value| value.fit.as_deref())
                .unwrap_or("cover");
            state.image = match fit {
                "inside" | "contain" => state.image.thumbnail(target_width, target_height),
                "fill" => {
                    state
                        .image
                        .resize_exact(target_width, target_height, FilterType::Lanczos3)
                }
                "outside" | "cover" => {
                    state
                        .image
                        .resize_to_fill(target_width, target_height, FilterType::Lanczos3)
                }
                _ => return Err(Error::from_reason(format!("Unsupported fit mode: {fit}"))),
            };
            Ok(())
        })?;
        Ok(this)
    }

    #[napi]
    pub fn jpeg(&self, this: This, quality: Option<u8>) -> Result<This> {
        self.with_state(|state| {
            state.output_format = ImageFormat::Jpeg;
            state.quality = quality.unwrap_or(80).clamp(1, 100);
            Ok(())
        })?;
        Ok(this)
    }

    #[napi]
    pub fn png(&self, this: This, _options: Option<PngOptions>) -> Result<This> {
        self.with_state(|state| {
            state.output_format = ImageFormat::Png;
            Ok(())
        })?;
        Ok(this)
    }

    #[napi]
    pub fn webp(&self, this: This, quality: Option<u8>) -> Result<This> {
        self.with_state(|state| {
            state.output_format = ImageFormat::WebP;
            state.quality = quality.unwrap_or(80).clamp(1, 100);
            Ok(())
        })?;
        Ok(this)
    }

    #[napi]
    pub async fn to_buffer(&self) -> Result<Buffer> {
        let state = {
            let mut guard = self
                .state
                .lock()
                .map_err(|_| Error::from_reason("ImageProcessor lock poisoned"))?;
            guard.take().ok_or_else(|| {
                Error::from_reason("ImageProcessor already consumed (toBuffer/dispose was called)")
            })?
        };
        encode_image(&state.image, state.output_format, state.quality).map(Buffer::from)
    }

    #[napi]
    pub fn dispose(&self) -> Result<()> {
        let mut guard = self
            .state
            .lock()
            .map_err(|_| Error::from_reason("ImageProcessor lock poisoned"))?;
        guard.take();
        Ok(())
    }
}

#[napi]
pub async fn process_image(input: Buffer) -> Result<ImageProcessor> {
    let format = image::guess_format(input.as_ref()).map_err(|error| {
        Error::from_reason(format!("Unable to determine image format: {error}"))
    })?;
    let image = image::load_from_memory_with_format(input.as_ref(), format)
        .map_err(|error| Error::from_reason(format!("Failed to decode image: {error}")))?;
    Ok(ImageProcessor {
        state: Arc::new(Mutex::new(Some(ImageState {
            image,
            source_format: format,
            output_format: format,
            quality: 80,
        }))),
    })
}

#[napi]
pub fn has_clipboard_image() -> bool {
    Clipboard::new()
        .and_then(|mut clipboard| clipboard.get_image())
        .is_ok()
}

#[napi]
pub fn read_clipboard_image(max_width: u32, max_height: u32) -> Result<Option<ClipboardImage>> {
    let mut clipboard = match Clipboard::new() {
        Ok(value) => value,
        Err(_) => return Ok(None),
    };
    let clipboard_image = match clipboard.get_image() {
        Ok(value) => value,
        Err(_) => return Ok(None),
    };
    let original_width = clipboard_image.width as u32;
    let original_height = clipboard_image.height as u32;
    let rgba = image::RgbaImage::from_raw(
        original_width,
        original_height,
        clipboard_image.bytes.into_owned(),
    )
    .ok_or_else(|| Error::from_reason("Clipboard image buffer has invalid dimensions"))?;
    let image = DynamicImage::ImageRgba8(rgba);
    let resized = image.thumbnail(max_width, max_height);
    let (width, height) = resized.dimensions();
    let png = encode_image(&resized, ImageFormat::Png, 80)?;
    Ok(Some(ClipboardImage {
        png: Buffer::from(png),
        original_width,
        original_height,
        width,
        height,
    }))
}

fn encode_image(image: &DynamicImage, format: ImageFormat, quality: u8) -> Result<Vec<u8>> {
    let mut output = Cursor::new(Vec::new());
    if format == ImageFormat::Jpeg {
        let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut output, quality);
        image
            .write_with_encoder(encoder)
            .map_err(|error| Error::from_reason(format!("Failed to encode image: {error}")))?;
    } else {
        image
            .write_to(&mut output, format)
            .map_err(|error| Error::from_reason(format!("Failed to encode image: {error}")))?;
    }
    Ok(output.into_inner())
}

fn format_name(format: ImageFormat) -> &'static str {
    match format {
        ImageFormat::Png => "png",
        ImageFormat::Jpeg => "jpeg",
        ImageFormat::Gif => "gif",
        ImageFormat::WebP => "webp",
        ImageFormat::Tiff => "tiff",
        ImageFormat::Bmp => "bmp",
        ImageFormat::Ico => "ico",
        _ => "unknown",
    }
}
