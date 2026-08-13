"""Desktop launcher: runs the Flask app in the background and opens it in a native window."""
import threading

import webview

from app import app, ensure_card_columns, ensure_puzzle_table

HOST = "127.0.0.1"
PORT = 5050


def start_server():
    ensure_card_columns()
    ensure_puzzle_table()
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    webview.create_window("Wacky Packages Vault", f"http://{HOST}:{PORT}", width=1200, height=800)
    webview.start()
