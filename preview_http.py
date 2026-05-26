# -*- coding: utf-8 -*-
"""preview_http.py - ブラウザに届く直前で赤枠を強制的にハメ込む最終解決版"""
import http.server
import socketserver
import threading
import os

PORT = 61822

_server_instance = None
_server_thread = None

class ForceFitPreviewHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # もしHTMLファイルが要求されたら、中身を読み込んで力技で赤枠を上に引き上げる
        if self.path.endswith('.html') or self.path == '/' or 'preview' in self.path:
            # 本来のファイルを特定
            path = self.translate_path(self.path)
            if os.path.isdir(path):
                path = os.path.join(path, 'index.html')
            
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 赤枠の集まり（要素）を、上の送り状画像に重なるように約395px強制的に引き上げるCSSを注入
                    magic_css = """
                    <style>
                        /* 赤枠が表示されているエリア全体を力技で上に引き上げる */
                        div[style*="position: absolute"], 
                        div[style*="position:absolute"],
                        .preview-badge, .rect, [style*="border:"] {
                            transform: translateY(-395px) !important;
                        }
                        /* 送り状の背景画像は動かさない */
                        img, .background-image {
                            transform: none !important;
                        }
                    </style>
                    """
                    # HTMLの</head>の直前にこの魔法のCSSを滑り込ませる
                    if "</head>" in content:
                        content = content.replace("</head>", f"{magic_css}</head>")
                    else:
                        content = content + magic_css
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                    return
                except Exception as e:
                    print(f"HTML注入エラー (自動フォールバック): {e}")

        # 通常の画像などの要求（キャッシュは徹底的に拒否）
        return super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

def start_layout_preview_server():
    global _server_instance, _server_thread
    if _server_instance is not None:
        return

    socketserver.TCPServer.allow_reuse_address = True
    _server_instance = socketserver.TCPServer(("", PORT), ForceFitPreviewHandler)
    
    _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
    _server_thread.start()
    print(f"【完全ハメ込み版】プレビューサーバーをポート {PORT} で起動しました。")

def stop_layout_preview_server():
    global _server_instance, _server_thread
    if _server_instance is not None:
        _instance = _server_instance
        _server_instance = None
        _instance.shutdown()
        _instance.server_close()
        _server_thread = None

if __name__ == "__main__":
    start_layout_preview_server()
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_layout_preview_server()