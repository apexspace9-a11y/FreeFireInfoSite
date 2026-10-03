import app as app_module
from protocol_hygiene import install_live_timestamp
from direct_guard import install_direct_guard

install_live_timestamp(app_module)
install_direct_guard(app_module)
app = app_module.app

if __name__ == '__main__':
    app.run(debug=True)
