import app as app_module
from ob55_upstream import install_ob55_upstream

install_ob55_upstream(app_module)
app = app_module.app

if __name__ == '__main__':
    app.run(debug=True)
