import json
import re
import time
import secrets
import logging

import requests
import yaml
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


class CaproverAPI:
    LOGIN_PATH = '/api/v2/login'
    SYSTEM_INFO_PATH = "/api/v2/user/system/info"
    APP_LIST_PATH = "/api/v2/user/apps/appDefinitions"
    APP_REGISTER_PATH = '/api/v2/user/apps/appDefinitions/register'
    APP_DELETE_PATH = '/api/v2/user/apps/appDefinitions/delete'
    ADD_CUSTOM_DOMAIN_PATH = '/api/v2/user/apps/appDefinitions/customdomain'
    UPDATE_APP_PATH = '/api/v2/user/apps/appDefinitions/update'
    ENABLE_SSL_PATH = '/api/v2/user/apps/appDefinitions/enablecustomdomainssl'
    APP_DATA_PATH = '/api/v2/user/apps/appData'

    PUBLIC_APP_PATH = "https://raw.githubusercontent.com/" \
                      "caprover/one-click-apps/master/public/v4/apps/"

    def __init__(
        self, dashboard_url: str, password: str,
        protocol: str = 'https://', schema_version: int = 2
    ):
        """
        :param dashboard_url: captain dashboard url
        :param password: captain dashboard password
        :param protocol: http protocol to use
        """
        self.session = requests.Session()
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'x-namespace': 'captain',
            'content-type': 'application/json;charset=UTF-8',
        }
        self.dashboard_url = dashboard_url.split("/#")[0].strip("/")
        self.password = password
        self.schema_version = schema_version
        self.base_url = self.dashboard_url if re.search(
            r"^https?://", self.dashboard_url
        ) else protocol + self.dashboard_url
        self.token = self._login()['data']['token']
        self.headers['x-captain-auth'] = self.token
        # root_domain with regex re.sub(r"^captain\.", "", self.dashboard_url)
        self.root_domain = self.get_system_info()['data']['rootDomain']

    def _build_url(self, api_endpoint):
        return self.base_url + api_endpoint

    @staticmethod
    def _check_errors(response):
        description = response.json().get('description', '')
        if response.json()['status'] != 100:
            logging.error(description)
            raise Exception(response.json()['description'])
        logging.info(description)
        return response.json()

    def _resolve_app_variables(
        self, one_click_app_name, cap_app_name,
        app_variables, automated: bool = False
    ):
        raw_app_data = requests.get(
            CaproverAPI.PUBLIC_APP_PATH + one_click_app_name + ".yml"
        ).text
        app_variables.update(
            {
                "$$cap_appname": cap_app_name,
                "$$cap_root_domain": self.root_domain
            }
        )
        _app_data = yaml.load(raw_app_data, Loader=Loader)

        variables = _app_data.get(
            "caproverOneClickApp", {}
        ).get("variables", {})
        for app_variable in variables:
            if app_variables.get(app_variable['id']) is None:
                default_value = app_variable.get('defaultValue', '')
                is_random_hex = re.search(
                    r"\$\$cap_gen_random_hex\((\d+)\)", default_value or ""
                )
                if is_random_hex:
                    default_value = secrets.token_hex(
                        int(is_random_hex.group(1))
                    )
                if not default_value and not automated:
                    ask_variable = "{label}:\n({description})\n".format(
                        label=app_variable['label'],
                        description=app_variable['description']
                    )
                    default_value = input(ask_variable)
                app_variables[app_variable['id']] = default_value
        for variable_id, variable_value in app_variables.items():
            raw_app_data = raw_app_data.replace(variable_id, str(variable_value))
        return raw_app_data

    def get_system_info(self):
        response = self.session.get(
            self._build_url(CaproverAPI.SYSTEM_INFO_PATH), headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    def get_app_info(self, app_name):
        logging.info("Getting app info...")
        response = self.session.get(
            self._build_url(CaproverAPI.APP_DATA_PATH) + '/' + app_name,
            headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    def _wait_until_app_ready(self, app_name, timeout=60):
        while timeout:
            try:
                app_info = self.get_app_info(app_name)
                if not app_info.get("data", {}).get("isAppBuilding"):
                    logging.info("App building finished...")
                    return
                logging.info("App is still building... sleeping for 1 second...")
            except Exception as e:
                logging.error(e)
            timeout -= 1
            time.sleep(1)
        raise Exception("App building timeout reached")

    def _ensure_app_build_success(self, app_name: str):
        app_info = self.get_app_info(app_name)
        if app_info.get("data", {}).get("isBuildFailed"):
            raise Exception("App building failed")
        return app_info

    def list_apps(self):
        response = self.session.get(
            self._build_url(CaproverAPI.APP_LIST_PATH),
            headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    def get_app(self, app_name: str):
        app_list = self.list_apps()
        for app in app_list.get('data').get("appDefinitions"):
            if app['appName'] == app_name:
                return app
        return dict

    def deploy_one_click_app(
        self, one_click_app_name: str, namespace: str,
        app_variables: dict = dict, automated: bool = False
    ):
        """
        :param one_click_app_name: one click app name
        :param namespace: a namespace to use for all services
            inside the one-click app
        :param app_variables: dict containing required app variables
        :param automated: set to true
            if you have supplied all required variables
        :return:
        """
        cap_app_name = "{}-{}".format(namespace, one_click_app_name)
        resolved_app_data = self._resolve_app_variables(
            one_click_app_name=one_click_app_name,
            cap_app_name=cap_app_name,
            app_variables=app_variables,
            automated=automated
        )
        app_data = yaml.load(resolved_app_data, Loader=Loader)
        services = app_data.get('services')
        for service_name, service_data in services.items():
            has_persistent_data = bool(service_data.get("volumes"))
            persistent_directories = service_data.get("volumes", [])
            environment_variables = service_data.get("environment", {})
            caprover_extras = service_data.get("caproverExtra", {})
            expose_as_web_app = True if caprover_extras.get(
                "notExposeAsWebApp", 'false') == 'false' else False
            container_http_port = int(
                caprover_extras.get("containerHttpPort", 80)
            )

            # create app
            self.create_app(
                app_name=service_name,
                has_persistent_data=has_persistent_data
            )

            # update app
            self.update_app(
                app_name=service_name,
                instance_count=1,
                persistent_directories=persistent_directories,
                environment_variables=environment_variables,
                expose_as_web_app=expose_as_web_app,
                container_http_port=container_http_port
            )

            data = {
                "captainDefinitionContent": {
                    "schemaVersion": self.schema_version
                },
                "gitHash": ""
            }
            image_name = service_data.get("image")
            docker_file_lines = caprover_extras.get("dockerfileLines")
            if image_name:
                data['captainDefinitionContent']['imageName'] = image_name
            elif docker_file_lines:
                data['captainDefinitionContent'][
                    'dockerfileLines'
                ] = docker_file_lines
            data['captainDefinitionContent'] = json.dumps(
                data['captainDefinitionContent']
            )
            return self.deploy_app(service_name, data)

    def deploy_app(self, app_name: str, deploy_instructions: dict):
        data = json.dumps(deploy_instructions)
        response = self.session.post(
            self._build_url(
                CaproverAPI.APP_DATA_PATH
            ) + '/' + app_name,
            headers=self.headers, data=data
        )
        self._check_errors(response)
        self._wait_until_app_ready(app_name=app_name, timeout=120)
        time.sleep(1)
        self._ensure_app_build_success(app_name=app_name)

    def _login(self):
        data = json.dumps({"password": self.password})
        logging.info("Attempting to login to caprover dashboard...")
        response = self.session.post(
            self._build_url(CaproverAPI.LOGIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    def stop_app(self, app_name: str):
        return self.update_app(app_name=app_name, instance_count=0)

    def delete_app(self, app_name, delete_volumes: bool = False):
        """
        :param app_name: app name
        :param delete_volumes: set to true to delete volumes
        :return:
        """
        if delete_volumes:
            app = self.get_app(app_name=app_name)
            data = json.dumps(
                {
                    "appName": app_name,
                    "volumes": [
                        volume['volumeName'] for volume in app['volumes']
                    ]
                }
            )
        else:
            data = json.dumps({"appName": app_name})
        response = requests.post(
            self._build_url(CaproverAPI.APP_DELETE_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    def create_app(
        self, app_name: str, has_persistent_data: bool = False,
        wait_for_app_build=True
    ):
        """
        :param app_name: app name
        :param has_persistent_data: true if requires persistent data
        :param wait_for_app_build: set false to skip waiting
        :return:
        """
        params = (
            ('detached', '1'),
        )
        data = json.dumps(
            {"appName": app_name, "hasPersistentData": has_persistent_data}
        )
        logging.info("Creating new app: {}".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.APP_REGISTER_PATH),
            headers=self.headers, params=params, data=data
        )
        if wait_for_app_build:
            self._wait_until_app_ready(app_name=app_name)
        return CaproverAPI._check_errors(response)

    def add_domain(self, app_name: str, custom_domain: str):
        """
        :param app_name:
        :param custom_domain:
        :return:
        """
        data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        logging.info("{} | Adding domain: {}".format(custom_domain, app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.ADD_CUSTOM_DOMAIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    def enable_ssl(self, app_name: str, custom_domain: str):
        """
        :param app_name: app name
        :param custom_domain: custom domain to add
        :return:
        """
        logging.info(
            "{} | Enabling SSL for domain {}".format(app_name, custom_domain)
        )
        data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        response = self.session.post(
            self._build_url(CaproverAPI.ENABLE_SSL_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    def update_app(
        self, app_name: str, instance_count: int = None,
        captain_definition_path: str = None,
        environment_variables: dict = None,
        expose_as_web_app: bool = None, force_ssl: bool = None,
        support_websocket: bool = None, port_mapping: list = None,
        persistent_directories: list = None, container_http_port: int = None,
        description: str = None, service_update_override: str = None,
        pre_deploy_function: str = None, app_push_webhook: dict = None
    ):
        """
        :param app_name: name of the app you want to update
        :param instance_count: instances count, set 0 to stop the app
        :param captain_definition_path: captain-definition file relative path
        :param environment_variables: dicts env variables
        :param expose_as_web_app: set true to expose the app as web app
        :param force_ssl: force traffic to use ssl
        :param support_websocket: set to true to enable webhook support
        :param port_mapping: list of port mapping
        :param persistent_directories: list
        :param container_http_port: port to use for your container app
        :param description: app description
        :param service_update_override: service override
        :param pre_deploy_function:
        :param app_push_webhook:
        :return: dict
        """
        if environment_variables:
            env_vars = [
                {
                    "key": k, "value": v
                } for k, v in environment_variables.items()
            ]
        else:
            env_vars = None
        if persistent_directories:
            volumes = [
                {
                    "volumeName": volume_data.split(':')[0], "containerPath": volume_data.split(':')[1]
                } for volume_data in persistent_directories
            ]
        else:
            volumes = None
        if port_mapping:
            ports = [
                {
                    "hostPort": host_port, "containerPort": container_port
                } for port in port_mapping
                for host_port, container_port in port.split(":")
            ]
        else:
            ports = None
        _data = {
            "appName": app_name,
            "instanceCount": instance_count,
            "preDeployFunction": pre_deploy_function,
            "captainDefinitionRelativeFilePath": captain_definition_path,
            "notExposeAsWebApp": not expose_as_web_app,
            "forceSsl": force_ssl,
            "websocketSupport": support_websocket,
            "volumes": volumes,
            "ports": ports,
            "containerHttpPort": container_http_port,
            "description": description,
            "appPushWebhook": app_push_webhook,
            "serviceUpdateOverride": service_update_override,
            "envVars": env_vars
        }
        data = {"appName": app_name}
        for k, v in _data.items():
            if v is None:
                continue
            data[k] = v
        logging.info("{} | Updating app info...".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.UPDATE_APP_PATH),
            headers=self.headers, data=json.dumps(data)
        )
        return CaproverAPI._check_errors(response)

    def create_and_update_app(
        self, app_name: str, has_persistent_data: bool,
        custom_domain: str = None, enable_ssl: bool = False, **kwargs
    ):
        """
        :param app_name: app name
        :param has_persistent_data: set to true to use persistent dirs
        :param custom_domain: custom domain for app
        :param enable_ssl: set to true to enable ssl
        :param kwargs: extra kwargs check
                :func:`~caprover_api.CaproverAPI.update_app`
        :return:
        """
        response = self.create_app(
            app_name=app_name, has_persistent_data=has_persistent_data
        )
        if custom_domain:
            time.sleep(0.10)
            response = self.add_domain(
                app_name=app_name, custom_domain=custom_domain
            )
        if enable_ssl:
            time.sleep(0.10)
            response = self.enable_ssl(
                app_name=app_name, custom_domain=custom_domain
            )
        if kwargs:
            time.sleep(0.10)
            response = self.update_app(app_name=app_name, **kwargs)
        return response

    def create_app_with_custom_domain(
        self, app_name: str, has_persistent_data: bool, custom_domain: str
    ):
        """
        :param app_name: app name
        :param has_persistent_data: set to true to use persistent dirs
        :param custom_domain: custom domain for app
        :return:
        """
        return self.create_and_update_app(
            app_name=app_name,
            has_persistent_data=has_persistent_data,
            custom_domain=custom_domain
        )

    def create_app_with_custom_domain_and_ssl(
        self, app_name: str, has_persistent_data: bool, custom_domain: str
    ):
        """
        :param app_name: app name
        :param has_persistent_data: set to true to use persistent dirs
        :param custom_domain: custom domain for app
        :return:
        """
        return self.create_and_update_app(
            app_name=app_name,
            has_persistent_data=has_persistent_data,
            custom_domain=custom_domain,
            enable_ssl=True
        )
