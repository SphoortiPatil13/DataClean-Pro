from flask import Flask
from flask_cors import CORS

from config import Config
from routes import api_bp

app = Flask(__name__)
app.config.from_object(Config)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("Set SECRET_KEY in the backend environment before starting DataCleanPro.")

CORS(app, origins=app.config["FRONTEND_ORIGINS"], supports_credentials=True)
app.register_blueprint(api_bp)


@app.route("/")
def home():
    return "DataCleanPro Backend is Running!"


if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])