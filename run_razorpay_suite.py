"""
AutoReconAI - Unified Razorpay Product Suite Runner
===================================================
Launches both Razorpay backend services simultaneously:
1. ⚡ Razorpay Payment Gateway Engine (Port 5051) -> Handles live payment checkouts & updates `payments` table.
2. 🚀 AutoReconAI 3-Way Matrix & AI Copilot Dashboard (Port 5055) -> Live Reconciliation & 4-Agent AI Controller.

Usage:
  python run_razorpay_suite.py
"""

import os
import sys
import subprocess
import time
import signal

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "AutoReconAI", "backend")

GATEWAY_SCRIPT = os.path.join(BACKEND_DIR, "gateway_server.py")
AUTORECON_SCRIPT = os.path.join(BACKEND_DIR, "app.py")

PYTHON_EXEC = sys.executable


def main():
    print("=" * 70)
    print("  🚀 LAUNCHING RAZORPAY AUTORECONAI & GATEWAY SUITE")
    print("=" * 70)
    print(f"  [1/2] ⚡ Starting Razorpay Gateway Server on  http://127.0.0.1:5051 ...")
    print(f"  [2/2] 🌐 Starting AutoReconAI Dashboard on      http://127.0.0.1:5055 ...")
    print("=" * 70)
    print("  Press Ctrl+C to cleanly stop both services at any time.\n")

    p_gateway = subprocess.Popen([PYTHON_EXEC, GATEWAY_SCRIPT], cwd=BACKEND_DIR)
    time.sleep(1.0)
    p_autorecon = subprocess.Popen([PYTHON_EXEC, AUTORECON_SCRIPT], cwd=BACKEND_DIR)

    try:
        while True:
            time.sleep(1.0)
            if p_gateway.poll() is not None:
                print("⚠️ Razorpay Gateway server stopped unexpectedly.")
                break
            if p_autorecon.poll() is not None:
                print("⚠️ AutoReconAI Dashboard server stopped unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Razorpay Suite...")
    finally:
        if p_gateway.poll() is None:
            p_gateway.terminate()
        if p_autorecon.poll() is None:
            p_autorecon.terminate()
        print("✅ Both services stopped cleanly.")


if __name__ == "__main__":
    main()
