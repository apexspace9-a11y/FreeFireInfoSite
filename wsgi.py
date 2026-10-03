import app as app_module
from protocol_hygiene import install_live_timestamp
from direct_guard import install_direct_guard

install_live_timestamp(app_module)
install_direct_guard(app_module)
app = app_module.app

_original_health = app.view_functions.get("health")
if _original_health is not None:
    def _health_with_timestamp_mode():
        response = _original_health()
        if isinstance(response, tuple):
            body, *rest = response
        else:
            body, rest = response, []
        try:
            payload = body.get_json()
            if isinstance(payload, dict):
                payload["majorLoginTimestampMode"] = getattr(
                    app_module, "MAJOR_LOGIN_TIMESTAMP_MODE", "legacy"
                )
                body.set_data(app.json.dumps(payload))
        except Exception:
            pass
        return (body, *rest) if rest else body

    app.view_functions["health"] = _health_with_timestamp_mode

if __name__ == '__main__':
    app.run(debug=True)
