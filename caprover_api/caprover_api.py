import json
import requests
import re
import time


class CaproverAPI:
    LOGIN_PATH = '/api/v2/login'
    APP_REGISTER_PATH = '/api/v2/user/apps/appDefinitions/register'
    ADD_CUSTOM_DOMAIN_PATH = '/api/v2/user/apps/appDefinitions/customdomain'
    UPDATE_APP_PATH = '/api/v2/user/apps/appDefinitions/update'
    ENABLE_SSL_PATH = '/api/v2/user/apps/appDefinitions/enablecustomdomainssl'

    def __init__(self, endpoint: str, password: str, protocol='https://'):
        """
        :param endpoint: captain dashboard endpoint
        :param password: captain dashboard password
        :param protocol: http protocol to use
        """
        self.session = requests.Session()
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'x-namespace': 'captain',
            'content-type': 'application/json;charset=UTF-8',
        }
        self.endpoint = endpoint.strip("/")
        self.password = password
        self.base_url = self.endpoint if re.search(
            r"^https?://", self.endpoint) else protocol + self.endpoint
        self.token = self.login()['data']['token']
        self.headers['x-captain-auth'] = self.token

    def build_url(self, api_endpoint):
        return self.base_url + api_endpoint

    @staticmethod
    def check_errors(response):
        if response.json()['status'] != 100:
            raise Exception(response.json()['description'])
        return response.json()

    def login(self):
        data = json.dumps({"password": self.password})
        response = self.session.post(
            self.build_url(CaproverAPI.LOGIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI.check_errors(response)

    def create_app(self, app_name: str, has_persistent_data: bool = False):
        """
        :param app_name:
        :param has_persistent_data:
        :return:
        """
        params = (
            ('detached', '1'),
        )
        data = json.dumps(
            {"appName": app_name, "hasPersistentData": has_persistent_data}
        )
        response = self.session.post(
            self.build_url(CaproverAPI.APP_REGISTER_PATH),
            headers=self.headers, params=params, data=data
        )
        return CaproverAPI.check_errors(response)

    def add_domain(self, app_name: str, custom_domain: str):
        """
        :param app_name:
        :param custom_domain:
        :return:
        """
        data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        response = self.session.post(
            self.build_url(CaproverAPI.ADD_CUSTOM_DOMAIN_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI.check_errors(response)

    def enable_ssl(self, app_name: str, custom_domain: str):
        data = json.dumps({"appName": app_name, "customDomain": custom_domain})
        response = self.session.post(
            self.build_url(CaproverAPI.ENABLE_SSL_PATH),
            headers=self.headers, data=data
        )
        return CaproverAPI.check_errors(response)

    def create_app_with_custom_domain(
        self, app_name: str, has_persistent_data: bool, custom_domain: str
    ):
        """
        :param app_name: name of the app
        :param has_persistent_data:
        :param custom_domain:
        :return:
        """
        self.create_app(
            app_name=app_name, has_persistent_data=has_persistent_data
        )
        time.sleep(0.10)
        return self.add_domain(app_name=app_name, custom_domain=custom_domain)

    def update_app(
        self, app_name: str, instance_count: int = None,
        captain_definition_path: str = None, env_vars: list = None,
        expose_as_web_app: bool = None, force_ssl: bool = None,
        support_websocket: bool = None, ports: list = None,
        volumes: list = None, container_http_port: int = None,
        description: str = None, service_update_override: str = None,
        pre_deploy_function: str = None, app_push_webhook: dict = None
    ):
        """
        :param app_name: name of the app you want to update
        :param instance_count: instances count, set 0 to stop the app
        :param captain_definition_path: captain-definition file relative path
        :param env_vars: list of dicts containing key, value for env variables
        :param expose_as_web_app: set true to expose the app as web app
        :param force_ssl: force traffic to use ssl
        :param support_websocket: set to true to enable webhook support
        :param ports: list of dicts containing keys hostPort and containerPort
        :param volumes: list
        :param container_http_port: port to use for your container app
        :param description: app description
        :param service_update_override: service override
        :param pre_deploy_function:
        :param app_push_webhook:
        :return: dict
        """
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
        response = self.session.post(
            self.build_url(CaproverAPI.UPDATE_APP_PATH),
            headers=self.headers, data=json.dumps(data)
        )
        return CaproverAPI.check_errors(response)

    def create_full_app_with_custom_domain(
        self, app_name: str, has_persistent_data: bool,
        custom_domain: str, enable_ssl: bool = False, **kwargs
    ):
        self.create_app_with_custom_domain(
            app_name=app_name, custom_domain=custom_domain,
            has_persistent_data=has_persistent_data
        )
        time.sleep(0.10)
        if enable_ssl:
            self.enable_ssl(app_name=app_name, custom_domain=custom_domain)
        return self.update_app(app_name=app_name, **kwargs)
