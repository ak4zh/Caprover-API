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

logging.basicConfig(level=logging.INFO)


class CaproverAPI:
    class Status:
        STATUS_ERROR_GENERIC = 1000
        STATUS_OK = 100
        STATUS_OK_DEPLOY_STARTED = 101
        STATUS_OK_PARTIALLY = 102
        STATUS_ERROR_CAPTAIN_NOT_INITIALIZED = 1001
        STATUS_ERROR_USER_NOT_INITIALIZED = 1101
        STATUS_ERROR_NOT_AUTHORIZED = 1102
        STATUS_ERROR_ALREADY_EXIST = 1103
        STATUS_ERROR_BAD_NAME = 1104
        STATUS_WRONG_PASSWORD = 1105
        STATUS_AUTH_TOKEN_INVALID = 1106
        VERIFICATION_FAILED = 1107
        ILLEGAL_OPERATION = 1108
        BUILD_ERROR = 1109
        ILLEGAL_PARAMETER = 1110
        NOT_FOUND = 1111
        AUTHENTICATION_FAILED = 1112
        STATUS_PASSWORD_BACK_OFF = 1113

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
    def _check_errors(response: dict):
        description = response.get('description', '')
        if response['status'] not in [
            CaproverAPI.Status.STATUS_OK,
            CaproverAPI.Status.STATUS_OK_PARTIALLY
        ]:
            logging.error(description)
            raise Exception(response['description'])
        logging.info(description)
        return response

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
                is_valid = re.search(
                    app_variable.get('validRegex', '.*').strip('/'),
                    default_value
                ) if default_value is not None else False
                is_invalid = not is_valid
                if is_invalid:
                    if automated:
                        raise Exception(
                            'Missing or Invalid value for >>{}<<'.format(
                                app_variable['id']
                            )
                        )
                    else:
                        ask_variable = "{label} [{description}]: ".format(
                            label=app_variable['label'],
                            description=app_variable.get('description', '')
                        )
                        default_value = input(ask_variable)
                app_variables[app_variable['id']] = default_value
        for variable_id, variable_value in app_variables.items():
            raw_app_data = raw_app_data.replace(
                variable_id, str(variable_value)
            )
        return raw_app_data

    def get_system_info(self):
        response = self.session.get(
            self._build_url(CaproverAPI.SYSTEM_INFO_PATH), headers=self.headers
        )
        return CaproverAPI._check_errors(response.json())

    def get_app_info(self, app_name):
        logging.info("Getting app info...")
        response = self.session.get(
            self._build_url(CaproverAPI.APP_DATA_PATH) + '/' + app_name,
            headers=self.headers
        )
        return CaproverAPI._check_errors(response.json())

    def _wait_until_app_ready(self, app_name, timeout=60):
        while timeout:
            try:
                app_info = self.get_app_info(app_name)
                if not app_info.get("data", {}).get("isAppBuilding"):
                    logging.info("App building finished...")
                    return
                logging.info(
                    "App is still building... sleeping for 1 second..."
                )
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
        return CaproverAPI._check_errors(response.json())

    def get_app(self, app_name: str):
        app_list = self.list_apps()
        for app in app_list.get('data').get("appDefinitions"):
            if app['appName'] == app_name:
                return app
        return {}

    def deploy_one_click_app(
        self, one_click_app_name: str, namespace: str,
        app_variables: dict = None, automated: bool = False
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
        app_variables = app_variables or {}
        cap_app_name = "{}-{}".format(namespace, one_click_app_name)
        resolved_app_data = self._resolve_app_variables(
            one_click_app_name=one_click_app_name,
            cap_app_name=cap_app_name,
            app_variables=app_variables,
            automated=automated
        )
        app_data = yaml.load(resolved_app_data, Loader=Loader)
        services = app_data.get('services')
        apps_to_deploy = list(services.keys())
        apps_deployed = []
        while set(apps_to_deploy) != set(apps_deployed):
            for service_name, service_data in services.items():
                depends_on = service_data.get('depends_on', [])
                if service_name in apps_deployed:
                    logging.info("app already deployed")
                    continue
                if not set(depends_on).issubset(set(apps_deployed)):
                    logging.info(
                        "Skipping because {} depends on {}".format(
                            service_name, ', '.join(depends_on)
                        )
                    )
                    continue
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
                image_name = service_data.get("image")
                docker_file_lines = caprover_extras.get("dockerfileLines")
                self.deploy_app(
                    service_name,
                    image_name=image_name,
                    docker_file_lines=docker_file_lines
                )
                apps_deployed.append(service_name)
        return CaproverAPI._check_errors(
            {
                "status": CaproverAPI.Status.STATUS_OK,
                "description": "Deployed all services in >>{}<<".format(
                    one_click_app_name
                )
            }
        )

    def deploy_app(
        self, app_name: str,
        image_name: str = None,
        docker_file_lines: list = None
    ):
        """
        :param app_name: app name
        :param image_name: docker hub image name
        :param docker_file_lines: docker file lines as list
        :return:
        """
        if image_name:
            definition = {
                "schemaVersion": self.schema_version,
                "imageName": image_name
            }
        elif docker_file_lines:
            definition = {
                "schemaVersion": self.schema_version,
                "dockerfileLines": docker_file_lines
            }
        else:
            definition = {}
        data = json.dumps({
            "captainDefinitionContent": json.dumps(definition),
            "gitHash": ""
        })
        response = self.session.post(
            self._build_url(
                CaproverAPI.APP_DATA_PATH
            ) + '/' + app_name,
            headers=self.headers, data=data
        )
        self._check_errors(response.json())
        self._wait_until_app_ready(app_name=app_name, timeout=120)
        time.sleep(0.50)
        self._ensure_app_build_success(app_name=app_name)
        return response.json()

    def _login(self):
        data = json.dumps({"password": self.password})
        logging.info("Attempting to login to caprover dashboard...")
        response = self.session.post(
            self._build_url(CaproverAPI.LOGIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response.json())

    def stop_app(self, app_name: str):
        return self.update_app(app_name=app_name, instance_count=0)

    def delete_app_matching_pattern(
        self, app_name_pattern: str, delete_volumes: bool = False,
        automated=False
    ):
        """
        :param app_name_pattern: regex pattern to match app name
        :param delete_volumes: set to true to delete volumes
        :param automated: set to tru to disable confirmation
        :return:
        """
        app_list = self.list_apps()
        for app in app_list.get('data').get("appDefinitions"):
            app_name = app['appName']
            if re.search(app_name_pattern, app_name):
                if not automated:
                    confirmation = None
                    while confirmation not in ['y', 'n', 'Y', 'N']:
                        confirmation = input(
                            "Do you want to delete app ({})?\n"
                            "Answer (Y or N): ".format(
                                app_name
                            )
                        )
                    if confirmation.lower() == 'n':
                        logging.info("Skipping app deletion...")
                        continue
                self.delete_app(
                    app_name=app['appName'], delete_volumes=delete_volumes
                )
                time.sleep(0.20)
        return {
            "description": "All apps matching pattern deleted",
            "status": CaproverAPI.Status.STATUS_OK
        }

    def delete_app(self, app_name, delete_volumes: bool = False):
        """
        :param app_name: app name
        :param delete_volumes: set to true to delete volumes
        :return:
        """
        if delete_volumes:
            logging.info(
                "Deleting app {} and it's volumes...".format(
                    app_name
                )
            )
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
            logging.info(
                "Deleting app {}".format(app_name)
            )
            data = json.dumps({"appName": app_name})
        response = requests.post(
            self._build_url(CaproverAPI.APP_DELETE_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response.json())

    def create_app(
        self, app_name: str,
        has_persistent_data: bool = False,
        wait_for_app_build: bool = True
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
        return CaproverAPI._check_errors(response.json())

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
        return CaproverAPI._check_errors(response.json())

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
        return CaproverAPI._check_errors(response.json())

    def update_app(
        self, app_name: str, instance_count: int = None,
        captain_definition_path: str = None,
        environment_variables: dict = None,
        expose_as_web_app: bool = None, force_ssl: bool = None,
        support_websocket: bool = None, port_mapping: list = None,
        persistent_directories: list = None, container_http_port: int = None,
        description: str = None, service_update_override: str = None,
        pre_deploy_function: str = None, app_push_webhook: dict = None,
        repo_info: dict = None
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
        :param repo_info: dict with repo info
            fields repo, user, password, sshKey, branch
        :return: dict
        """
        current_app_info = self.get_app(app_name=app_name)
        if not current_app_info.get("appPushWebhook"):
            current_app_info["appPushWebhook"] = {}
        if repo_info and isinstance(repo_info, dict):
            current_app_info["appPushWebhook"]["repoInfo"] = repo_info

        # handle environment_variables
        # gets current envVars and overwrite with new data
        current_env_vars = current_app_info["envVars"]
        current_env_vars_as_dict = {
            item['key']: item['value'] for item in current_env_vars
        }
        if environment_variables:
            current_env_vars_as_dict.update(environment_variables)
        updated_environment_variables = [
            {
                "key": k, "value": v
            } for k, v in current_env_vars_as_dict.items()
        ]
        current_app_info['envVars'] = updated_environment_variables

        # handle volumes
        # gets current volumes and overwrite with new data
        current_volumes = current_app_info['volumes']
        current_volumes_as_dict = {
            item['volumeName']: item['containerPath'] for
            item in current_volumes
        }
        if persistent_directories:
            for volume_pair in persistent_directories:
                volume_name, container_path = volume_pair.split(':')
                current_volumes_as_dict[volume_name] = container_path
        updated_volumes = [
            {
                "volumeName": volume_name,
                "containerPath": container_path
            } for
            volume_name, container_path in current_volumes_as_dict.items()
        ]
        current_app_info['volumes'] = updated_volumes

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
            "ports": ports,
            "containerHttpPort": container_http_port,
            "description": description,
            "appPushWebhook": app_push_webhook,
            "serviceUpdateOverride": service_update_override,
        }
        for k, v in _data.items():
            if v is None:
                # skip as value not changed
                continue
            # update current value with new value
            current_app_info[k] = v
        logging.info("{} | Updating app info...".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.UPDATE_APP_PATH),
            headers=self.headers, data=json.dumps(current_app_info)
        )
        return CaproverAPI._check_errors(response.json())

    def create_and_update_app(
        self, app_name: str, has_persistent_data: bool = False,
        custom_domain: str = None, enable_ssl: bool = False,
        image_name: str = None, docker_file_lines: list = None,
        instance_count: int = 1, **kwargs
    ):
        """
        :param app_name: app name
        :param has_persistent_data: set to true to use persistent dirs
        :param custom_domain: custom domain for app
        :param enable_ssl: set to true to enable ssl
        :param image_name: docker hub image name
        :param docker_file_lines: docker file lines
        :param instance_count: int number of instances to run
        :param kwargs: extra kwargs check
                :func:`~caprover_api.CaproverAPI.update_app`
        :return:
        """
        if kwargs.get("persistent_directories"):
            has_persistent_data = True
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
            response = self.update_app(
                app_name=app_name,
                instance_count=instance_count,
                **kwargs
            )
        if image_name or docker_file_lines:
            response = self.deploy_app(
                app_name=app_name,
                image_name=image_name,
                docker_file_lines=docker_file_lines
            )
        return response

    def create_app_with_custom_domain(
        self, app_name: str,
        custom_domain: str,
        has_persistent_data: bool = False,
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
        self, app_name: str,
        custom_domain: str,
        has_persistent_data: bool = False,
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
