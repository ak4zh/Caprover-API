=====
Usage
=====

To use Caprover API in a project::

    from caprover_api import caprover_api

    cap = caprover_api.CaproverAPI(
        dashboard_url="cap-dashboard-url",
        password="cap-dashboard-password"
    )


One Click Apps
^^^^^^^^^^^^^^^

get app name from `List of one-click-apps <https://github.com/caprover/one-click-apps/tree/master/public/v4/apps>`_

automated deploy::

    app_variables = {
        "$$cap_redis_password": "REDIS-PASSWORD-HERE"
    }
    cap.deploy_one_click_app(
        one_click_app_name='redis',
        namespace='new-app',
        app_variables=app_variables,
        automated=True
    )


manual deploy (you will be asked to enter required variables during runtime)::

    cap.deploy_one_click_app(
        one_click_app_name='redis',
        namespace='new-app',
    )


Custom Apps
^^^^^^^^^^^^

create a new app::

    cap.create_app(
        app_name="new-app",
        has_persistent_data=False
    )


deploy app from docker hub::

    # app must already exists
    cap.deploy_app(
        app_name="new-app",
        image_name='redis:5'
    )


App CRUD (Create, Update, Delete)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

add domain to an existing app::

    cap.add_domain(
        app_name="new-app",
        custom_domain="my-app.example.com"
    )

enable ssl::

    cap.enable_ssl(
        app_name='new-app',
        custom_domain='my-app.example.com'
    )

add environment variables to app::

    environment_variables = {
        "key1": "val1",
        "key2": "val2"
    }
    cap.update_app(
        app_name='new-app',
        environment_variables=environment_variables
    )

add environment variables and volumes to app::

    environment_variables = {
        "key1": "val1",
        "key2": "val2"
    }
    persistent_directories = [
        "volumeName:/pathInApp",
        "volumeNameTwo:/pathTwoInApp"
    ]
    cap.update_app(
        app_name='new-app',
        environment_variables=environment_variables,
        persistent_directories=persistent_directories
    )

add environment variables and volumes to app::

    environment_variables = {
        "key1": "val1",
        "key2": "val2"
    }
    persistent_directories = [
        "volumeName:/pathInApp",
        "volumeNameTwo:/pathTwoInApp"
    ]
    port_mapping = [
        "serverPort:containerPort",
    ]
    cap.update_app(
        app_name='new-app',
        environment_variables=environment_variables,
        persistent_directories=persistent_directories,
        port_mapping=port_mapping
    )

create app and add custom domain::

    cap.create_and_update_app(
        app_name="new-app",
        has_persistent_data=False,
        custom_domain="my-app.example.com"
    )

create app with custom domain and enable ssl::

    cap.create_and_update_app(
        app_name="new-app",
        has_persistent_data=False,
        custom_domain="my-app.example.com",
        enable_ssl=True
    )


create app and deploy redis from docker hub::

    cap.create_and_update_app(
        app_name="new-app",
        has_persistent_data=False,
        image_name='redis:5',
        persistent_directories=['new-app-redis-data:/data', ]
    )


delete an app::

    cap.delete_app(app_name="new-app")

delete an app and it's volumes::

    cap.delete_app(
        app_name="new-app", delete_volumes=True
    )

delete apps matching regex pattern (with confirmation)::

    cap.delete_app_matching_pattern(
        app_name_pattern=".*new-app.*",
        delete_volumes=True
    )

delete apps matching regex pattern (☠️ without confirmation)::

    cap.delete_app_matching_pattern(
        app_name_pattern=".*new-app.*",
        delete_volumes=True,
        automated=True
    )

stop an app temporarily::

    cap.stop_app(app_name="new-app")

start a temporarily stopped app::

    cap.update_app(app_name="new-app", instance_count=1)

scale app to 3 instances::

    cap.update_app(app_name="new-app", instance_count=3)


Backup
^^^^^^

Create a backup of CapRover configs in order to be able to spin up a clone of this server.
Note that your application data (volumes, and images) are not part of this backup. This backup only includes the server configuration details, such as root domains, app names, SSL certs and etc.::

    cap.create_backup()

You can pass an optional file_name, the default file name is `{captain_namespace}-bck-%Y-%m-%d %H:%M:%S.rar`

