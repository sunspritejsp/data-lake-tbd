import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"
ROW_LIMIT = 50000
SUPERSET_WEBSERVER_TIMEOUT = 120
BABEL_DEFAULT_LOCALE = "pt_BR"
LANGUAGES = {"pt_BR": {"flag": "br", "name": "Português (BR)"}, "en": {"flag": "us", "name": "English"}}
D3_FORMAT = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["R$ ", ""]}
EXTRA_CATEGORICAL_COLOR_SCHEMES = [{
    "id": "lake",
    "label": "Lake (segura para daltonismo)",
    "description": "",
    "isDefault": True,
    "colors": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
}]
