import datetime
import functools
import json
import logging
import os
import re
import secrets
import time
from collections import Counter, namedtuple

import requests
import yaml


class TooManyRequestsError(Exception):
    """Raised when we encounter HTTP 429 response from CapRover.

    CapRover uses this status to do its own locking to prevent certain
    concurrent operations.
    There's no problem retrying it until the lock is released.
    """
    pass


RetrySettings = namedtuple("RetrySettings", ("times", "delay"))

# Retry behavior depends on what happened:
# - TooManyRequestsError -> 15s delay, max 6 tries
# - requests.ConnectionError -> 1s delay, max 3 tries
TRANSIENT_ERRORS = {
    TooManyRequestsError: RetrySettings(6, 15),
    requests.exceptions.ConnectionError: RetrySettings(3, 1),
}


def retry(exception_settings: dict[Exception, RetrySettings]):
    """
    Retry Decorator
    Retries the wrapped function/method if the exceptions that key
    ``exception_settings`` are thrown.

    :param exception_settings: exceptions that trigger a retry attempt,
        mapping to the retry configuration for that exception.
        Retry tracking is per-class in this dict.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries_by_exc = Counter()

            while True:
                try:
                    return func(*args, **kwargs)
                except tuple(exception_settings.keys()) as e:
                    # Determine the exc type to look up its settings.
                    # Must iteratively call isinstance to be inheritance-aware.
                    for key, settings in exception_settings.items():
                        if isinstance(e, key):
                            exc_type = key
                            break

                    if retries_by_exc[exc_type] < settings.times:
                        retries_by_exc[exc_type] += 1
                        logging.error(
                            "%s raised %s. "
                            "Waiting %ds before retry attempt %d of %d",
                            func.__name__,
                            exc_type.__name__,
                            settings.delay,
                            retries_by_exc[exc_type],
                            settings.times,
                        )
                        time.sleep(settings.delay)
                    else:
                        raise  # exhausted retries
        return wrapper
    return decorator


PUBLIC_ONE_CLICK_APP_PATH = "https://oneclickapps.caprover.com/v4/apps/"

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
    APP_LIST_PROJECTS = "/api/v2/user/projects"    
    APP_REGISTER_PATH = '/api/v2/user/apps/appDefinitions/register'
    APP_DELETE_PATH = '/api/v2/user/apps/appDefinitions/delete'
    ADD_CUSTOM_DOMAIN_PATH = '/api/v2/user/apps/appDefinitions/customdomain'
    UPDATE_APP_PATH = '/api/v2/user/apps/appDefinitions/update'
    ENABLE_BASE_DOMAIN_SSL_PATH = '/api/v2/user/apps/appDefinitions/enablebasedomainssl'
    ENABLE_CUSTOM_DOMAIN_SSL_PATH = '/api/v2/user/apps/appDefinitions/enablecustomdomainssl'
    APP_DATA_PATH = '/api/v2/user/apps/appData'
    CREATE_BACKUP_PATH = '/api/v2/user/system/createbackup'
    DOWNLOAD_BACKUP_PATH = '/api/v2/downloads/'
    TRIGGER_BUILD_PATH = '/api/v2/user/apps/webhooks/triggerbuild'

    def __init__(
        self, dashboard_url: str, password: str,
        protocol: str = 'https://', schema_version: int = 2,
        captain_namespace='captain'
    ):
        """
        :param dashboard_url: captain dashboard url
        :param password: captain dashboard password
        :param protocol: http protocol to use
        """
        self.session = requests.Session()
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'x-namespace': captain_namespace,
            'content-type': 'application/json;charset=UTF-8',
        }
        self.dashboard_url = dashboard_url.split("/#")[0].strip("/")
        self.password = password
        self.captain_namespace = captain_namespace
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
    def _check_errors(response: requests.Response):
        # Check for HTTP status code 429, which is likely to
        # be retried because it's in COMMON_ERRORS.
        if response.status_code == 429:
            raise TooManyRequestsError(
                f"HTTP 429 Too Many Requests for {response.url}"
            )

        response_json = response.json()
        description = response_json.get('description', '')
        if response_json['status'] not in [
            CaproverAPI.Status.STATUS_OK,
            CaproverAPI.Status.STATUS_OK_PARTIALLY
        ]:
            logging.error(description)
            raise Exception(description)
        logging.info(description)
        return response_json

    @staticmethod
    def _download_one_click_app_defn(repository_path: str, one_click_app_name: str):
        """Retrieve the raw app definition from the public one-click app repository.

        :return raw_app_definition (str) containing JSON
        """
        r = requests.get(
            repository_path + one_click_app_name
        )
        r.raise_for_status()
        return r.text

    def _resolve_app_variables(
        self, raw_app_definition, cap_app_name,
        app_variables, automated: bool = False
    ):
        """
        Resolve the app variables for a CapRover one-click app.

        The function injects the `app_variables` into the app definiition,
        including resolving default values and random hex generator expressions.

        If required variables are missing or have an invalid value, the function will
        either raise an exception (if `automated` is True) or prompt the user to enter a
        valid value.

        :param raw_app_definition (str): The unparsed JSON text of the one-click app definition.
        :param cap_app_name (str): The name under which the app will be installed.
        :param app_variables (dict): A dictionary of $$cap_variables and their values.
                This will get updated to also include the $$cap_appname and $$cap_root domain.
        :param automated (bool, optional): Whether the function is being called in an
                automated context. Defaults to False.

        :return The updated raw app definiton with all variables resolved.
        """
        raw_app_data = raw_app_definition
        # Replace any random hex generators in the raw data first
        for match in re.finditer(r"\$\$cap_gen_random_hex\((\d+)\)", raw_app_data):
            requested_length = int(match.group(1))
            raw_app_data = raw_app_data.replace(
                match.group(0),
                # slice notation is because secrets.token_hex generates the hex
                # representation of n bytes, which is twice as many hex chars.
                secrets.token_hex(requested_length)[:requested_length]
            )

        app_variables.update(
            {
                "$$cap_appname": cap_app_name,
                "$$cap_root_domain": self.root_domain
            }
        )
        _app_data = json.loads(raw_app_data)

        variables = _app_data.get(
            "caproverOneClickApp", {}
        ).get("variables", {})
        for app_variable in variables:
            if app_variables.get(app_variable['id']) is None:
                default_value = app_variable.get('defaultValue', '')
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

    @staticmethod
    def _parse_command(command):
        """
        Parse Docker Compose service command into a Docker override.

        The override is compatible with Docker API's Service Update Object
        and therefore is a valid Caprover Service Update Override.

        Mimics caprover-frontend's functionality from:
        https://github.com/caprover/caprover-frontend/blob/ffb2b69c1143262a241cd8005dddf263eece6bb1/src/utils/DockerComposeToServiceOverride.ts#L37

        :param command: The command from the Docker Compose service definition
            a string or a list of str
        :return: A dict that can be converted to YAML for the service override.
        """

        def parse_docker_cmd(cmd_string):
            # Matches sequences inside quotes or sequences without spaces
            regex = r'[^\s"\'\n]+|"([^"]*)"|\'([^\']*)\''
            args = []
            for match in re.finditer(regex, cmd_string):
                args.append(match.group(1) or match.group(2) or match.group(0))
            return args

        # Convert command to a list if it is a string
        command_list = (
            command if isinstance(command, list) else parse_docker_cmd(command)
        )

        # Build the service override dictionary
        return {"TaskTemplate": {"ContainerSpec": {"Command": command_list}}}

    @retry(TRANSIENT_ERRORS)
    def get_system_info(self):
        response = self.session.get(
            self._build_url(CaproverAPI.SYSTEM_INFO_PATH), headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def get_app_info(self, app_name):
        logging.info("Getting app info...")
        response = self.session.get(
            self._build_url(CaproverAPI.APP_DATA_PATH) + '/' + app_name,
            headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def _wait_until_app_ready(self, app_name):
        timeout = 60
        while timeout:
            timeout -= 1
            time.sleep(1)
            app_info = self.get_app_info(app_name)
            if not app_info.get("data", {}).get("isAppBuilding"):
                logging.info("App building finished...")
                return app_info
        raise Exception("App building timeout reached")

    def _ensure_app_build_success(self, app_name: str):
        app_info = self.get_app_info(app_name)
        if app_info.get("data", {}).get("isBuildFailed"):
            raise Exception("App building failed")
        return app_info

    @retry(TRANSIENT_ERRORS)
    def list_apps(self):
        response = self.session.get(
            self._build_url(CaproverAPI.APP_LIST_PATH),
            headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def list_projects(self):
        response = self.session.get(
            self._build_url(CaproverAPI.APP_LIST_PROJECTS),
            headers=self.headers
        )
        return CaproverAPI._check_errors(response)

    def get_app(self, app_name: str):
        app_list = self.list_apps()
        for app in app_list.get('data').get("appDefinitions"):
            if app['appName'] == app_name:
                return app
        return {}

    def deploy_one_click_app(
        self,
        one_click_app_name: str,
        app_name: str = None,
        app_variables: dict = None,
        automated: bool = False,
        one_click_repository: str = PUBLIC_ONE_CLICK_APP_PATH,
        tags: list[str] = None,
    ):
        """
        Deploys a one-click app on the CapRover platform.

        :param one_click_app_name: one click app name in the repository
        :param app_name: The name under which the app will be installed.
            (optional) If unset, the `one_click_app_name` will be used.
        :param app_variables: dict containing required app variables
        :param automated: set to true
            if you have supplied all required variables
        :param one_click_repository: where to download the one-click app from
        :param tags: list of tags to apply to all services
            (optional) If unset (None), a tag with the app_name will be used.
            Pass an empty list to create no tags.
        :return dict containing the deployment "status" and "description".
        """
        app_variables = app_variables or {}
        if not app_name:
            app_name = one_click_app_name

        # Default tag is the app_name if no custom tags provided
        if tags is None:
            tags = [app_name]

        raw_app_definition = self._download_one_click_app_defn(
            one_click_repository, one_click_app_name
        )
        resolved_app_data = self._resolve_app_variables(
            raw_app_definition=raw_app_definition,
            cap_app_name=app_name,
            app_variables=app_variables,
            automated=automated
        )
        app_data = json.loads(resolved_app_data)
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

                # Parse command (if it exists) into service update override
                command = service_data.get("command")
                service_update_override = None
                if command:
                    service_override_dict = self._parse_command(command)
                    service_update_override = yaml.dump(
                        service_override_dict, default_style="|"
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
                    container_http_port=container_http_port,
                    serviceUpdateOverride=service_update_override,
                    tags=tags,
                )
                image_name = service_data.get("image")
                docker_file_lines = caprover_extras.get("dockerfileLines")
                self.deploy_app(
                    service_name,
                    image_name=image_name,
                    docker_file_lines=docker_file_lines
                )
                apps_deployed.append(service_name)
        return {
            "status": CaproverAPI.Status.STATUS_OK,
            "description": "Deployed all services in >>{}<<".format(
                one_click_app_name
            )
        }

    @retry(TRANSIENT_ERRORS)
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
        self._check_errors(response)
        self._wait_until_app_ready(app_name=app_name)
        time.sleep(0.50)
        self._ensure_app_build_success(app_name=app_name)
        return response.json()

    @retry(TRANSIENT_ERRORS)
    def _login(self):
        data = json.dumps({"password": self.password})
        logging.info("Attempting to login to caprover dashboard...")
        response = self.session.post(
            self._build_url(CaproverAPI.LOGIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def stop_app(self, app_name: str):
        return self.update_app(app_name=app_name, instance_count=0)

    def delete_app_matching_pattern(
        self, app_name_pattern: str,
        delete_volumes: bool = False,
        automated: bool = False
    ):
        """
        :param app_name_pattern: regex pattern to match app name
        :param delete_volumes: set to true to delete volumes
        :param automated: set to true to disable confirmation
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

    @retry(TRANSIENT_ERRORS)
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
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def create_app(
        self, app_name: str,
        project_id: str = '',
        has_persistent_data: bool = False,
        wait_for_app_build: bool = True
    ):
        """
        :param app_name: app name
        :param project_id: leave it emtpy to create in root <no parent project>
        :param has_persistent_data: true if requires persistent data
        :param wait_for_app_build: set false to skip waiting
        :return:
        """
        params = (
            ('detached', '1'),
        )
        data = json.dumps(
            {"appName": app_name, "projectId": project_id, "hasPersistentData": has_persistent_data}
        )
        logging.info("Creating new app: {}".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.APP_REGISTER_PATH),
            headers=self.headers, params=params, data=data
        )
        if wait_for_app_build:
            self._wait_until_app_ready(app_name=app_name)
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def add_domain(self, app_name: str, custom_domain: str):
        """
        :param app_name:
        :param custom_domain: custom domain to add
            It must already point to this IP in DNS
        :return:
        """
        data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        logging.info("{} | Adding domain: {}".format(custom_domain, app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.ADD_CUSTOM_DOMAIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def enable_ssl(self, app_name: str, custom_domain: str = None):
        """Enable SSL on a domain.

        :param app_name: app name
        :param custom_domain: if set, SSL is enabled on this custom domain.
            Otherwise, SSL is enabled on the base domain.
        :return:
        """
        if custom_domain:
            logging.info(
                "{} | Enabling SSL for domain {}".format(app_name, custom_domain)
            )
            path = CaproverAPI.ENABLE_CUSTOM_DOMAIN_SSL_PATH
            data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        else:
            logging.info(
                "{} | Enabling SSL for root domain".format(app_name)
            )
            path = CaproverAPI.ENABLE_BASE_DOMAIN_SSL_PATH
            data = json.dumps({"appName": app_name})
        response = self.session.post(
            self._build_url(path),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    @retry(TRANSIENT_ERRORS)
    def update_app(
        self,
        app_name: str,
        project_id: str = None,
        instance_count: int = None,
        captain_definition_path: str = None,
        environment_variables: dict = None,
        expose_as_web_app: bool = None,
        force_ssl: bool = None,
        support_websocket: bool = None,
        port_mapping: list = None,
        persistent_directories: list = None,
        container_http_port: int = None,
        description: str = None,
        service_update_override: str = None,
        pre_deploy_function: str = None,
        app_push_webhook: dict = None,
        repo_info: dict = None,
        http_auth: dict = None,
        tags: list[str] = None,
        **kwargs,
    ):
        """
        :param app_name: name of the app you want to update
        :param project_id: project id of the project you want to move this app to
        :param instance_count: instances count, set 0 to stop the app
        :param captain_definition_path: captain-definition file relative path
        :param environment_variables: dict of env variables
            will be merged with the current set:
            There is no way to DELETE an env variable from this API.
        :param expose_as_web_app: set true to expose the app as web app
        :param force_ssl: force traffic to use ssl
        :param support_websocket: set to true to enable webhook support
        :param port_mapping: list of port mapping
        :param persistent_directories: list of dict
            fields hostPath OR volumeName, containerPath
            If a list is passed, it replaces the entire set of persistent
              directories on the app.
            Set to None (default) to leave as-is, or empty list to clear
              existing mounts.
        :param container_http_port: port to use for your container app
        :param description: app description
        :param service_update_override: service override
        :param pre_deploy_function:
        :param app_push_webhook:
        :param repo_info: dict with repo info
            fields repo, user, password, sshKey, branch
        :param http_auth: dict with http auth info
            fields user, password
        :param tags: list of strings to set as the app tags, allowing to better
            group and view your apps in the table.
            If a list is passed, it replaces the entire set of tags on the app.
            Set to None (default) to leave tags as-is,
            or pass an empty list to clear existing tags.
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
        if persistent_directories is not None:
            updated_volumes = []
            for volume_pair in persistent_directories:
                volume_name, container_path = volume_pair.split(':')
                if volume_name.startswith("/"):
                    updated_volumes.append(
                        {
                            "hostPath": volume_name,
                            "containerPath": container_path,
                        }
                    )
                else:
                    updated_volumes.append(
                        {
                            "volumeName": volume_name,
                            "containerPath": container_path,
                        }
                    )
            persistent_directories = updated_volumes

        if port_mapping:
            ports = [
                {
                    "hostPort": ports.split(':')[0],
                    "containerPort": ports.split(':')[1]
                } for ports in port_mapping
            ]
        else:
            ports = None
        _data = {
            "appName": app_name,
            "projectId": project_id,
            "instanceCount": instance_count,
            "preDeployFunction": pre_deploy_function,
            "captainDefinitionRelativeFilePath": captain_definition_path,
            "notExposeAsWebApp": None if expose_as_web_app is None else (not expose_as_web_app),
            "forceSsl": force_ssl,
            "websocketSupport": support_websocket,
            "ports": ports,
            "volumes": persistent_directories,
            "containerHttpPort": container_http_port,
            "description": description,
            "appPushWebhook": app_push_webhook,
            "serviceUpdateOverride": service_update_override,
            "httpAuth": http_auth,
            "tags": None if tags is None else [{"tagName": t} for t in tags],
        }
        for k, v in _data.items():
            if v is None:
                # skip as value not changed
                continue
            # update current value with new value
            current_app_info[k] = v

        # Any other kwarg is an automatic override.
        current_app_info.update(kwargs)

        logging.info("{} | Updating app info...".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.UPDATE_APP_PATH),
            headers=self.headers, data=json.dumps(current_app_info)
        )
        return CaproverAPI._check_errors(response)

    def create_and_update_app(
        self, app_name: str, project_id: str = '', 
        has_persistent_data: bool = False,
        custom_domain: str = None, enable_ssl: bool = False,
        image_name: str = None, docker_file_lines: list = None,
        instance_count: int = 1, **kwargs
    ):
        """
        :param app_name: app name
        :param project_id: leave it emtpy to create in root <no parent project>
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
            app_name=app_name, project_id=project_id,
            has_persistent_data=has_persistent_data
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
                project_id=project_id,
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

    def _create_backup(self, file_name):
        data = json.dumps({"postDownloadFileName": file_name})
        response = self.session.post(
            self._build_url(CaproverAPI.CREATE_BACKUP_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI._check_errors(response)

    def _download_backup(self, download_token, file_name):
        response = self.session.get(
            self._build_url(CaproverAPI.DOWNLOAD_BACKUP_PATH),
            headers=self.headers,
            params={
                'namespace': self.captain_namespace,
                'downloadToken': download_token
            }
        )
        assert response.status_code == 200
        with open(file_name, 'wb') as f:
            f.write(response.content)
            return os.path.abspath(f.name)

    def create_backup(self, file_name=None):
        if not file_name:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_name = f'{self.captain_namespace}-bck-{date_str}.rar'

        valid_response = self._create_backup(file_name=file_name)
        download_token = valid_response.get('data', {}).get('downloadToken')
        return self._download_backup(
            download_token=download_token, file_name=file_name
        )

    def trigger_build(self, app_name: str, captain_namespace: str = 'captain'):
        app = self.get_app(app_name=app_name)
        push_web_token = app.get('appPushWebhook', {}).get('pushWebhookToken')
        params = (
            ('namespace', captain_namespace),
            ('token', push_web_token)
        )
        data = '{}'
        logging.info("Triggering build process: {}".format(app_name))
        response = self.session.post(
            self._build_url(CaproverAPI.TRIGGER_BUILD_PATH),
            headers=self.headers, params=params, data=data
        )
        return CaproverAPI._check_errors(response)
