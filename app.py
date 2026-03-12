"""
Rotection web server
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    print("=" * 55)
    print("  ROTECTION - WEB DASHBOARD RUNNING LOCALLY")
    print("  Open http://localhost:5050 in your browser")
    print("  An API Key is NOT required to use this, although you can use one.")
    print("=" * 55)
    app.run(debug=False, port=5050, threaded=True)
