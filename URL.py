import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sqlite3
import hashlib
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os

class URLShortener:
    def __init__(self):
        self.db_name = "url_shortener.db"
        self.server_port = 8080
        self.server_running = False
        self.server_thread = None
        self.httpd = None
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                short_code TEXT UNIQUE NOT NULL,
                original_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                click_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
    
    def generate_short_code(self, url):
        """Generate a short code for the URL"""
        hash_object = hashlib.md5(url.encode())
        return hash_object.hexdigest()[:6]
    
    def add_url(self, original_url):
        """Add a new URL to the database"""
        if not original_url.startswith(('http://', 'https://')):
            original_url = 'http://' + original_url
        
        short_code = self.generate_short_code(original_url)
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO urls (short_code, original_url) VALUES (?, ?)",
                (short_code, original_url)
            )
            conn.commit()
            return short_code
        except sqlite3.IntegrityError:
            # If short code already exists, return the existing one
            cursor.execute(
                "SELECT short_code FROM urls WHERE original_url = ?",
                (original_url,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()
    
    def get_original_url(self, short_code):
        """Get original URL by short code"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT original_url FROM urls WHERE short_code = ?",
            (short_code,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def increment_click_count(self, short_code):
        """Increment click count for a short URL"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?",
            (short_code,)
        )
        conn.commit()
        conn.close()
    
    def get_all_urls(self):
        """Get all URLs with analytics"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT short_code, original_url, created_at, click_count FROM urls ORDER BY created_at DESC"
        )
        results = cursor.fetchall()
        conn.close()
        return results

class RedirectHandler(BaseHTTPRequestHandler):
    def __init__(self, url_shortener, *args, **kwargs):
        self.url_shortener = url_shortener
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        path = self.path.lstrip('/')
        
        if path == '':
            # Serve a simple home page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <head><title>URL Shortener</title></head>
            <body>
                <h1>URL Shortener Service</h1>
                <p>This is a local URL shortener service running on port 8080.</p>
                <p>Use the GUI application to create short URLs.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            return
        
        # Look up the short code
        original_url = self.url_shortener.get_original_url(path)
        
        if original_url:
            # Increment click count
            self.url_shortener.increment_click_count(path)
            
            # Redirect to original URL
            self.send_response(301)
            self.send_header('Location', original_url)
            self.end_headers()
        else:
            # 404 - Short URL not found
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <head><title>URL Not Found</title></head>
            <body>
                <h1>404 - URL Not Found</h1>
                <p>The short URL you requested does not exist.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

class URLShortenerGUI:
    def __init__(self, root):
        self.root = root
        self.shortener = URLShortener()
        self.setup_ui()
        self.start_server()
        
    def setup_ui(self):
        self.root.title("URL Shortener")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="URL Shortener", font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # URL input section
        ttk.Label(main_frame, text="Enter URL to shorten:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=50)
        self.url_entry.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.shorten_btn = ttk.Button(main_frame, text="Shorten URL", command=self.shorten_url)
        self.shorten_btn.grid(row=2, column=2, padx=(10, 0), pady=(0, 10))
        
        # Result section
        ttk.Label(main_frame, text="Shortened URL:").grid(row=3, column=0, sticky=tk.W, pady=(10, 5))
        
        self.result_var = tk.StringVar()
        self.result_entry = ttk.Entry(main_frame, textvariable=self.result_var, state='readonly', width=50)
        self.result_entry.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.copy_btn = ttk.Button(main_frame, text="Copy", command=self.copy_result, state='disabled')
        self.copy_btn.grid(row=4, column=2, padx=(10, 0), pady=(0, 10))
        
        self.open_btn = ttk.Button(main_frame, text="Open", command=self.open_result, state='disabled')
        self.open_btn.grid(row=5, column=2, padx=(10, 0), pady=(0, 10))
        
        # Analytics section
        ttk.Label(main_frame, text="URL Analytics:", font=('Arial', 12, 'bold')).grid(row=6, column=0, sticky=tk.W, pady=(20, 10))
        
        # Treeview for analytics
        columns = ('Short Code', 'Original URL', 'Created', 'Clicks')
        self.tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=12)
        
        # Define headings
        for col in columns:
            self.tree.heading(col, text=col)
            
        # Configure column widths
        self.tree.column('Short Code', width=100)
        self.tree.column('Original URL', width=300)
        self.tree.column('Created', width=150)
        self.tree.column('Clicks', width=80)
        
        self.tree.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=7, column=3, sticky=(tk.N, tk.S), pady=(0, 10))
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Configure grid weights for resizing
        main_frame.rowconfigure(7, weight=1)
        
        # Refresh button
        self.refresh_btn = ttk.Button(main_frame, text="Refresh Analytics", command=self.refresh_analytics)
        self.refresh_btn.grid(row=8, column=0, pady=(10, 0))
        
        # Server status
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground='green')
        self.status_label.grid(row=8, column=1, columnspan=2, sticky=tk.E, pady=(10, 0))
        
        # Load initial data
        self.refresh_analytics()
        
        # Bind Enter key to shorten URL
        self.url_entry.bind('<Return>', lambda e: self.shorten_url())
    
    def start_server(self):
        """Start the HTTP server in a separate thread"""
        def run_server():
            try:
                def handler(*args, **kwargs):
                    RedirectHandler(self.shortener, *args, **kwargs)
                
                self.shortener.httpd = HTTPServer(('localhost', self.shortener.server_port), handler)
                self.shortener.server_running = True
                self.status_var.set(f"Server running on http://localhost:{self.shortener.server_port}")
                self.shortener.httpd.serve_forever()
            except Exception as e:
                self.status_var.set(f"Server error: {str(e)}")
        
        self.shortener.server_thread = threading.Thread(target=run_server, daemon=True)
        self.shortener.server_thread.start()
    
    def shorten_url(self):
        """Shorten the entered URL"""
        url = self.url_var.get().strip()
        
        if not url:
            messagebox.showerror("Error", "Please enter a URL to shorten.")
            return
        
        try:
            short_code = self.shortener.add_url(url)
            if short_code:
                short_url = f"http://localhost:{self.shortener.server_port}/{short_code}"
                self.result_var.set(short_url)
                self.copy_btn.config(state='normal')
                self.open_btn.config(state='normal')
                self.refresh_analytics()
                messagebox.showinfo("Success", f"URL shortened successfully!\nShort URL: {short_url}")
            else:
                messagebox.showerror("Error", "Failed to shorten URL.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
    
    def copy_result(self):
        """Copy the shortened URL to clipboard"""
        result = self.result_var.get()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
            messagebox.showinfo("Copied", "Shortened URL copied to clipboard!")
    
    def open_result(self):
        """Open the shortened URL in browser"""
        result = self.result_var.get()
        if result:
            webbrowser.open(result)
    
    def refresh_analytics(self):
        """Refresh the analytics table"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Get all URLs
        urls = self.shortener.get_all_urls()
        
        for url_data in urls:
            short_code, original_url, created_at, click_count = url_data
            # Truncate long URLs for display
            display_url = original_url[:50] + "..." if len(original_url) > 50 else original_url
            self.tree.insert('', 'end', values=(short_code, display_url, created_at, click_count))
    
    def on_closing(self):
        """Handle application closing"""
        if self.shortener.httpd:
            self.shortener.httpd.shutdown()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = URLShortenerGUI(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_closing()

if __name__ == "__main__":
    main()