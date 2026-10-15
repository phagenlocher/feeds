# List just recipes
list-recipes:
    @just --list


# Install frontend dependencies (always via corepack's pnpm)
ui-install:
    cd crates/feeds-app/ui && corepack pnpm install

# Build the frontend into crates/feeds-app/ui/dist
ui-build: ui-install
    cd crates/feeds-app/ui && corepack pnpm build

# Alias ensuring the embedded frontend exists before cargo builds the app
_ui: ui-build

# Format all files
format:
    cargo fmt --all

# Lint all files
lint: _ui
    cargo clippy --workspace --all-targets -- -D warnings

# Run all tests
test: _ui
    cargo test --workspace

# Build a release binary (workspace)
build: _ui
    cargo build --release --workspace --features feeds-app/custom-protocol

# Build all Tauri bundles (requires the tauri CLI)
bundle: ui-build
    cd crates/feeds-app && cargo tauri build

# Build a portable Linux AppImage (installs the tauri CLI on first use)
appimage: ui-build
    @command -v cargo-tauri >/dev/null 2>&1 || cargo install tauri-cli
    cd crates/feeds-app && cargo tauri build --bundles appimage
    @echo "AppImage: target/release/bundle/appimage/"

# Build and install the app binary to ~/.local/bin
install: build
    cp target/release/feeds-app ~/.local/bin/feeds

# Run the app with given arguments
run *args: _ui
    cargo run -p feeds-app --features custom-protocol -- {{args}}

# Regenerate THIRD-PARTY-NOTICES (installs cargo-about on first use)
notices:
    @command -v cargo-about >/dev/null 2>&1 || cargo install cargo-about --locked --features cli
    python3 scripts/gen-notices.py
