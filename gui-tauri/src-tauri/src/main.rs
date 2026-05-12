// GUI 方案 A：Tauri 2.x — 原生桌面应用
//
// 构建: cd gui-tauri && cargo tauri build
// 开发: cd gui-tauri && cargo tauri dev
//
// 特点:
// - ~5MB 包体积（vs Electron ~120MB）
// - 系统托盘 + 全局快捷键 + 原生通知
// - WebView 内嵌 React（复用 webui-react 的组件）
// - Rust 后端管理 Python Core SDK 子进程

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use std::process::Command;

#[tauri::command]
async fn quick_capture(text: String) -> Result<String, String> {
    let output = Command::new("python")
        .args(["-c", &format!(
            "import asyncio; from memory_os.agents.sensory_gateway import SensoryGateway; \
             print(asyncio.run(SensoryGateway(...).ingest('{}', 'tauri-gui')))",
            text
        )])
        .output()
        .map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![quick_capture])
        .setup(|app| {
            let _window = app.get_webview_window("main").unwrap();

            // 注册全局快捷键
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            app.plugin(
                tauri_plugin_global_shortcut::Builder::new()
                    .with_shortcut("CmdOrCtrl+Shift+M")?
                    .build(),
            )?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
