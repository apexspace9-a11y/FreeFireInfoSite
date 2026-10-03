import app as app_module
from direct_guard import install_direct_guard

install_direct_guard(app_module)
app = app_module.app

if __name__ == '__main__':
    app.run(debug=True)
