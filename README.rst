============
Caprover API
============


.. image:: https://img.shields.io/pypi/v/caprover_api.svg
        :target: https://pypi.python.org/pypi/caprover_api

.. image:: https://img.shields.io/travis/ak4zh/caprover_api.svg
        :target: https://travis-ci.com/ak4zh/caprover_api

.. image:: https://readthedocs.org/projects/caprover-api/badge/?version=latest
        :target: https://caprover-api.readthedocs.io/en/latest/?version=latest
        :alt: Documentation Status




unofficial caprover api to deploy apps to caprover


* Free software: MIT license
* Full Documentation: https://caprover-api.readthedocs.io.


Features
--------

* create app
* add custom domain
* enable ssl
* update app with port mappings, env variables, repo info etc
* deploy one click apps
* get list of all apps
* get app by name
* delete app
* delete app and it's volumes
* stop app
* scale app


Usage
-----

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


create and deploy redis app from docker hub::

    cap.create_and_update_app(
        app_name="new-app-redis",
        has_persistent_data=False,
        image_name='redis:5',
        persistent_directories=['new-app-redis-data:/data', ]
    )

