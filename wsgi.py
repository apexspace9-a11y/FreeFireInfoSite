import app as app_module
from player_info_fallback import install_player_info_fallback

install_player_info_fallback(app_module)
app = app_module.app

if __name__ == '__main__':
    app.run(debug=True)
