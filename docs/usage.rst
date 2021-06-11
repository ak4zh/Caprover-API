=====
Usage
=====

To use Caprover API in a project::

    from caprover_api import caprover_api

    cap = caprover_api.CaproverAPI(endpoint="your-cap-dashboard-url", password="your-cap-dashboard-password")

    # to create a new app
    cap.create_app(app_name="new-app", has_persistent_data=False)

    # to create app and add custom domain
    cap.create_app_with_custom_domain(app_name="new-app", has_persistent_data=False, custom_domain="my-app.example.com")

    # enable ssl
    cap.enable_ssl(app_name='new-app', custom_domain='my-app.example.com')

    # to create app with custom domain and enable ssl
    cap.create_full_app_with_custom_domain(
        app_name="new-app", has_persistent_data=False, custom_domain="my-app.example.com", enable_ssl=True
    )

