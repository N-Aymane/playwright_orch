#!/usr/bin/env python3
"""
scratch/test_server.py — A lightweight local HTTP test server for validating the framework.

Serves two versions of a registration form:
  /           → Version A: standard HTML form with clear IDs/names
  /mutated    → Version B: mutated form with changed/missing IDs (to trigger self-healing)
  /success    → A confirmation page returned after form submission

Run with:
    python scratch/test_server.py

Then point the framework at:
    python main.py --url "http://localhost:8765" --goal "Register a new user account"

Or test self-healing against the mutated form:
    python main.py --url "http://localhost:8765/mutated" --goal "Register a new user account on the mutated form"
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json

HOST = "localhost"
PORT = 8765

# --- Version A: Clean, well-structured registration form ---
FORM_V1_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Register | Test App (Version A)</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #f0f0f0;
    }
    .card {
      background: rgba(255,255,255,0.07);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 16px;
      padding: 48px;
      width: 480px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    h1 { font-size: 1.9rem; margin-bottom: 8px; color: #a78bfa; }
    .subtitle { font-size: 0.9rem; color: #94a3b8; margin-bottom: 32px; }
    label { display: block; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 6px; margin-top: 18px; }
    input, select { 
      width: 100%; padding: 12px 14px; border-radius: 8px; 
      background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2);
      color: #f1f5f9; font-size: 0.95rem; outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: #a78bfa; }
    select option { background: #1e1b4b; }
    .submit-btn {
      margin-top: 28px;
      width: 100%;
      padding: 14px;
      background: linear-gradient(90deg, #6366f1, #a855f7);
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      letter-spacing: 0.03em;
      transition: opacity 0.2s, transform 0.1s;
    }
    .submit-btn:hover { opacity: 0.9; transform: translateY(-1px); }
    .version-badge {
      position: fixed; top: 16px; right: 16px; background: #10b981;
      color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
    }
  </style>
</head>
<body>
  <span class="version-badge">Form Version A</span>
  <div class="card">
    <h1>Create Account</h1>
    <p class="subtitle">Join us today and start your journey</p>
    <form id="registration-form" action="/submit" method="POST">
      <label for="first-name">First Name</label>
      <input type="text" id="first-name" name="first_name" placeholder="Enter your first name" required />

      <label for="last-name">Last Name</label>
      <input type="text" id="last-name" name="last_name" placeholder="Enter your last name" required />

      <label for="email">Email Address</label>
      <input type="email" id="email" name="email" placeholder="you@example.com" required />

      <label for="phone">Phone Number</label>
      <input type="tel" id="phone" name="phone" placeholder="555-000-1234" />

      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Create a strong password" required />

      <label for="country">Country</label>
      <select id="country" name="country">
        <option value="">Select a country</option>
        <option value="us">United States</option>
        <option value="gb">United Kingdom</option>
        <option value="ca">Canada</option>
        <option value="au">Australia</option>
      </select>

      <button type="submit" class="submit-btn" id="register-btn">Create Account</button>
    </form>
  </div>
</body>
</html>"""

# --- Version B: Mutated form (different IDs/names) — triggers self-healing ---
FORM_V2_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Register | Test App (Version B - Mutated)</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #1a0000, #3d0000, #1a0000);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #f0f0f0;
    }
    .card {
      background: rgba(255,255,255,0.07);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255,100,100,0.25);
      border-radius: 16px;
      padding: 48px;
      width: 480px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    h1 { font-size: 1.9rem; margin-bottom: 8px; color: #f87171; }
    .subtitle { font-size: 0.9rem; color: #94a3b8; margin-bottom: 32px; }
    label { display: block; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 6px; margin-top: 18px; }
    input, select { 
      width: 100%; padding: 12px 14px; border-radius: 8px; 
      background: rgba(255,255,255,0.08); border: 1px solid rgba(255,100,100,0.3);
      color: #f1f5f9; font-size: 0.95rem; outline: none;
    }
    input:focus, select:focus { border-color: #f87171; }
    select option { background: #1e0a0a; }
    .submit-btn {
      margin-top: 28px; width: 100%; padding: 14px;
      background: linear-gradient(90deg, #dc2626, #ef4444);
      color: white; border: none; border-radius: 8px;
      font-size: 1rem; font-weight: 600; cursor: pointer;
    }
    .version-badge {
      position: fixed; top: 16px; right: 16px; background: #dc2626;
      color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
    }
  </style>
</head>
<body>
  <span class="version-badge">Form Version B (Mutated)</span>
  <div class="card">
    <h1>Sign Up Now</h1>
    <p class="subtitle">IDs and attributes have been changed (healing test)</p>
    <form id="signup-form" action="/submit" method="POST">
      <!-- first-name → fname_field, last-name → lname_input, email → user_email_addr -->
      <label for="fname_field">First Name</label>
      <input type="text" id="fname_field" name="fname" placeholder="First name" required />

      <label for="lname_input">Last Name</label>
      <input type="text" id="lname_input" name="lname" placeholder="Last name" required />

      <label for="user_email_addr">Email Address</label>
      <input type="email" id="user_email_addr" name="user_email" placeholder="Email" required />

      <label for="mobile_no">Mobile Number</label>
      <input type="tel" id="mobile_no" name="mobile" placeholder="Mobile number" />

      <label for="user_pass">Create Password</label>
      <input type="password" id="user_pass" name="user_password" placeholder="Strong password" required />

      <label for="region">Region</label>
      <select id="region" name="region">
        <option value="">Choose region</option>
        <option value="us">United States</option>
        <option value="gb">United Kingdom</option>
        <option value="ca">Canada</option>
        <option value="au">Australia</option>
      </select>

      <button type="submit" class="submit-btn" id="submit-btn">Sign Up</button>
    </form>
  </div>
</body>
</html>"""

# --- Success Page ---
SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Registration Successful</title>
  <style>
    body {
      font-family: 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #064e3b, #065f46, #022c22);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      color: #f0f0f0;
    }
    .card {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 16px; padding: 56px; text-align: center;
      box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    }
    .icon { font-size: 4rem; margin-bottom: 20px; }
    h1 { font-size: 2rem; color: #10b981; margin-bottom: 12px; }
    p { color: #94a3b8; font-size: 1rem; line-height: 1.6; }
    .data-box {
      background: rgba(0,0,0,0.2); border-radius: 8px;
      padding: 16px; margin-top: 24px; text-align: left; font-size: 0.85rem;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🎉</div>
    <h1>Registration Successful!</h1>
    <p>Welcome aboard! Your account has been created successfully.</p>
    <div class="data-box" id="confirmation-message">
      ✅ Account created and verified. You may now log in.
    </div>
  </div>
</body>
</html>"""


class TestServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  [SERVER] {self.address_string()} - {format % args}")

    def send_html(self, content: str, status: int = 200):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_html(FORM_V1_HTML)
        elif path == "/mutated":
            self.send_html(FORM_V2_HTML)
        elif path == "/success":
            self.send_html(SUCCESS_HTML)
        else:
            self.send_html("<h1>404 Not Found</h1>", status=404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/submit":
            # Parse form data and redirect to success
            content_length = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(content_length)
            # Redirect to success page
            self.send_response(302)
            self.send_header("Location", "/success")
            self.end_headers()
        else:
            self.send_html("<h1>404 Not Found</h1>", status=404)


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TestServerHandler)
    print(f"\n{'='*60}")
    print(f"  🚀 Test Server running at http://{HOST}:{PORT}")
    print(f"{'='*60}")
    print(f"  Endpoints:")
    print(f"    /          → Registration Form (Version A — clean)")
    print(f"    /mutated   → Registration Form (Version B — mutated IDs)")
    print(f"    /success   → Success confirmation page")
    print(f"\n  Usage:")
    print(f"    python main.py --url \"http://{HOST}:{PORT}\" \\")
    print(f"      --goal \"Test user registration form with valid inputs\"")
    print(f"\n  Press Ctrl+C to stop.")
    print(f"{'='*60}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Test server stopped.")
