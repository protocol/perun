from flask import Flask
from routes import bp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024
app.register_blueprint(bp)
