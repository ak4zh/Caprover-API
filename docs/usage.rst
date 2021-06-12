=====
Usage
=====

To use Caprover API in a project::

    from caprover_api import caprover_api

    cap = caprover_api.CaproverAPI(
        dashboard_url="cap-dashboard-url",
        password="cap-dashboard-password"
    )

    # to create a new app
    cap.create_app(
        app_name="new-app", has_persistent_data=False
    )

    # to add domain a new app
    cap.add_domain(
        app_name="new-app", custom_domain="my-app.example.com"
    )

    # enable ssl
    cap.enable_ssl(
        app_name='new-app', custom_domain='my-app.example.com'
    )

    # add environment variables to app
    env_vars = {"key1": "val1", "key2": "val2"}
    cap.update_app(app_name='new-app', env_vars=env_vars)

    # add environment variables and volumes to app
    environment_variables = {"key1": "val1", "key2": "val2"}
    persistent_directories = [
        "volumeName:/pathInApp", "volumeNameTwo:/pathTwoInApp"
    ]
    cap.update_app(
        app_name='new-app',
        environment_variables=environment_variables,
        persistent_directories=persistent_directories
    )

    # add environment variables and volumes to app
    environment_variables = {"key1": "val1", "key2": "val2"}
    persistent_directories = [
        "volumeName:/pathInApp", "volumeNameTwo:/pathTwoInApp"
    ]
    port_mapping = ["serverPort:containerPort", ]
    cap.update_app(
        app_name='new-app',
        environment_variables=environment_variables,
        persistent_directories=persistent_directories,
        port_mapping=port_mapping
    )

    # to create app and add custom domain
    cap.create_and_update_app(
        app_name="new-app", has_persistent_data=False,
        custom_domain="my-app.example.com"
    )

    # to create app with custom domain and enable ssl
    cap.create_and_update_app(
        app_name="new-app", has_persistent_data=False,
        custom_domain="my-app.example.com", enable_ssl=True
    )

    # one click apps
    # get app name from
    # https://github.com/caprover/one-click-apps/tree/master/public/v4/apps

    # automated deploy
    app_variables = {"$$cap_redis_password": "REDIS-PASSWORD-HERE"}
    cap.deploy_one_click_app(
        one_click_app_name='redis',
        namespace='new-app',
        app_variables=app_variables,
        automated=True
    )

    # manual deploy
    # you will be asked to enter required variables during runtime
    cap.deploy_one_click_app(
        one_click_app_name='redis',
        namespace='new-app',
    )

    # to delete an app
    cap.delete_app(app_name="new-app")

    # to delete an app and it's volumes
    cap.delete_app(
        app_name="new-app", delete_volumes=True
    )

    # to delete apps matching regex pattern
    # with confirmation
    cap.delete_app_matching_pattern(
        app_name_pattern=".*new-app.*",
        delete_volumes=True
    )

    # to delete apps matching regex pattern
    # ☠️ without confirmation
    cap.delete_app_matching_pattern(
        app_name_pattern=".*new-app.*",
        delete_volumes=True,
        automated=True
    )

    # to stop an app temporarily
    cap.stop_app(app_name="new-app")

    # to scale app to 3 instances
    cap.stop_app(app_name="new-app", instance_count=3)

