from flask import Flask
from views import bp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(port=5000)
