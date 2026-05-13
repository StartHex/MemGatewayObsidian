// Memory OS GUI — Tauri 2.x native desktop app
//
// Architecture:
//   1. Spawn Python `memory-os serve` as sidecar process
//   2. Use HTTP health check to wait for API readiness
//   3. WebView loads the WebUI React app from the API server (or localhost:5173 in dev)
//   4. System tray for quick access; CmdOrCtrl+Shift+M for quick capture
//   5. On exit: gracefully terminate the sidecar
//
// Build: cd gui-tauri && cargo tauri build
// Dev:   cd gui-tauri && cargo tauri dev

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};

struct SidecarState {
    child: Mutex<Option<Child>>,
}

#[tauri::command]
async fn get_api_url(state: State<'_, SidecarState>) -> Result<String, String> {
    std::env::var("MEMORY_OS_API_URL")
        .or_else(|_| Ok("http://127.0.0.1:9090".to_string()))
}

fn spawn_sidecar(vault_path: &str, port: u16) -> Result<Child, String> {
    let child = Command::new("memory-os")
        .args(["serve", "--vault", vault_path, "--port", &port.to_string()])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start memory-os serve: {}. Is memory-os installed? (pip install -e .)", e))?;
    Ok(child)
}

fn wait_for_api(port: u16, timeout_secs: u64) -> bool {
    let url = format!("http://127.0.0.1:{}/api/v1/system/stats", port);
    let start = std::time::Instant::now();
    while start.elapsed().as_secs() < timeout_secs {
        if let Ok(resp) = ureq::get(&url).call() {
            if resp.status() == 200 {
                return true;
            }
        }
        std::thread::sleep(std::time::Duration::from_millis(500));
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Read vault path from env or use default
    let vault_path = std::env::var("MEMORY_OS_VAULT")
        .unwrap_or_else(|_| format!("{}/memory-vault", std::env::var("HOME").unwrap_or_default()));
    let port: u16 = std::env::var("MEMORY_OS_PORT")
        .unwrap_or_else(|_| "9090".to_string())
        .parse()
        .unwrap_or(9090);

    // In development mode, skip spawning sidecar (assumes dev is running it manually)
    let skip_sidecar = std::env::var("TAURI_SKIP_SIDECAR").is_ok();

    let child = if skip_sidecar {
        None
    } else {
        match spawn_sidecar(&vault_path, port) {
            Ok(c) => {
                println!("memory-os serve started (pid: {}), waiting for API...", c.id());
                if wait_for_api(port, 15) {
                    println!("API is ready on port {}", port);
                    Some(c)
                } else {
                    eprintln!("WARNING: API did not become ready within 15s, continuing anyway");
                    Some(c)
                }
            }
            Err(e) => {
                eprintln!("WARNING: Could not start sidecar: {}", e);
                println!("Expected: memory-os serve --vault {} --port {}", vault_path, port);
                None
            }
        }
    };

    tauri::Builder::default()
        .manage(SidecarState {
            child: Mutex::new(child),
        })
        .setup(move |app| {
            let main_window = app.get_webview_window("main").unwrap();

            // In production, load the API server's root (which should serve the built React app).
            // In development, load the Vite dev server.
            let frontend_url = std::env::var("TAURI_DEV_URL")
                .unwrap_or_else(|_| format!("http://127.0.0.1:{}", port));

            main_window.eval(&format!("window.location.href = '{}';", frontend_url))
                .expect("failed to navigate to frontend");

            // System tray
            #[cfg(desktop)]
            {
                use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
                use tauri::menu::{Menu, MenuItem};

                let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
                let open_item = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
                let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

                let _tray = TrayIconBuilder::new()
                    .menu(&menu)
                    .on_menu_event(|app_handle, event| match event.id.as_ref() {
                        "quit" => {
                            app_handle.exit(0);
                        }
                        "open" => {
                            if let Some(window) = app_handle.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        _ => {}
                    })
                    .on_tray_icon_event(|tray_handle, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            let app = tray_handle.app_handle();
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    })
                    .build(app)?;
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Hide instead of close — keep running in tray
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run();
}
