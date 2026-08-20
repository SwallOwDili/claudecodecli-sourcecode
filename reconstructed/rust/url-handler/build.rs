fn main() {
    napi_build::setup();
    println!("cargo:rustc-link-framework=ApplicationServices");
}
