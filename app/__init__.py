from flask import Flask
from dotenv import load_dotenv
from pathlib import Path

def create_app(test_config=None):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    app = Flask(__name__, instance_relative_config=False)
    app.config.update(JSON_SORT_KEYS=False)
    if test_config:
        app.config.update(test_config)
    from .database import init_db
    from .routes import bp
    init_db()
    app.register_blueprint(bp)
    return app
