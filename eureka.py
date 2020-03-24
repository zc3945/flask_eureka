# coding:utf-8
import logging
import time
import re
import subprocess
from threading import Thread
from platform import python_version

import requests
from flask import Blueprint, jsonify


__all__ = ['Eureka']

if python_version().split('.')[0] == '2':
    def getoutput(cmd):
        return subprocess.check_output([cmd], shell=True)
else:
    def getoutput(cmd):
        return subprocess.getoutput(cmd)


logger = logging.getLogger("eureka")
logger.setLevel(logging.DEBUG)
st = logging.StreamHandler()
fmt = logging.Formatter("%(asctime)s - [%(name)s] - %(levelname)s - %(message)s")
st.setFormatter(fmt)
logger.addHandler(st)


class EurekaRuntimeError(RuntimeError):
    pass


class EurekaClient(object):

    def __init__(self, name, eureka_url=None, ip_address=None, port=None, heartbeat_interval=None, get_ip_cmd=None):
        self.app_name = name
        self.eureka_url = eureka_url[:-1] if eureka_url.endswith('/') else eureka_url
        self.heartbeat_interval = heartbeat_interval or 30
        self.service_path = 'eureka/apps'
        self.port = port

        self.ip_address = ip_address
        if not self.ip_address:
            self.ip_address = getoutput(get_ip_cmd).strip() if get_ip_cmd else '127.0.0.1'
        if not re.match('^(\d{1,3}\.){3}\d{1,3}$', self.ip_address):
            raise EurekaRuntimeError('本地ip地址获取错误,请检查 GET_IP_CMD 命令是否正确')
        self.other_apps = {}

    def get_instance_id(self):
        return '{}:{}'.format(self.ip_address, self.port)

    def get_instance_data(self):
        """生成注册服务所需的数据结构"""
        return {
            'instance': {
                'app': self.app_name,
                'instanceId': self.get_instance_id(),
                'hostName': self.ip_address,
                'ipAddr': self.ip_address,
                'healthCheckUrl': 'http://{}:{}/health'.format(self.ip_address, self.port),
                'statusPageUrl': 'http://{}:{}/info'.format(self.ip_address, self.port),
                'homePageUrl': 'http://{}:{}/info'.format(self.ip_address, self.port),
                'port': {
                    '$': self.port,
                    '@enabled': 'true',
                },
                'vipAddress': self.app_name,
                'dataCenterInfo': {
                    '@class': 'com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo',
                    'name': 'MyOwn',
                },
            },
        }

    def star(self):
        """注册服务"""
        self.register()
        self.heartbeat_task = Thread(target=self.hearthbeat)
        self.heartbeat_task.daemon = True
        self.heartbeat_task.start()

    def hearthbeat(self):
        """新线程"""
        while True:
            time.sleep(self.heartbeat_interval)
            try:
                self.renew()
            except Exception as exc:
                logger.error('心跳发送失败', exc_info=exc)

    def register(self, initial_status="UP"):
        """注册服务"""
        instance_data = self.get_instance_data()
        instance_data['instance']['status'] = initial_status

        try:
            url = '{}/{}/{}'.format(self.eureka_url, self.service_path, self.app_name)
            response = requests.post(url, json=instance_data)
            response.raise_for_status()
            logger.info('服务注册成功!!')
        except Exception as exc:
            raise EurekaRuntimeError('eureka注册失败，{}'.format(str(exc)))

    def renew(self):
        """发送心跳"""
        try:
            url = '{}/{}/{}/{}'.format(self.eureka_url, self.service_path, self.app_name, self.get_instance_id())
            response = requests.put(url)
        except Exception as exc:
            raise EurekaRuntimeError('eureka连接异常，{}'.format(str(exc)))
        else:
            if response.status_code == 404:
                self.register()
            elif response.status_code > 300:
                raise EurekaRuntimeError('eureka连接异常，状态码:{}'.format(response.status_code))

    def get_from_any_instance(self, endpoint):
        """获取注册在eureka上的服务,解析成dict"""
        try:
            url = '{}/{}'.format(self.eureka_url, endpoint)
            response = requests.get(url, headers={'accept': 'application/json'})
            data = response.json()
        except Exception as exc:
            raise EurekaRuntimeError('eureka获取服务地址异常，{}'.format(str(exc)))
        else:
            app_list = {}
            if data:
                for app in data['applications']['application']:
                    now_ok = [f"http://{i['ipAddr']}:{i['port']['$']}" for i in app['instance'] if i['status'] == 'UP']
                    if now_ok:
                        app_list[app['name']] = now_ok

            self.other_apps.update(app_list)
            logger.debug('更新其他服务状态')

    def fetch_registry(self):
        """获取服务地址"""
        while True:
            try:
                self.get_from_any_instance("eureka/apps")
            except Exception as exc:
                logger.error('更新其他服务失败', exc_info=exc)
            time.sleep(self.heartbeat_interval)

    def star_fetch_registry(self):
        """新线程"""
        self.heartbeat_task = Thread(target=self.fetch_registry)
        self.heartbeat_task.daemon = True
        self.heartbeat_task.start()


eureka_bp = Blueprint('eureka', __name__)


@eureka_bp.route('/info')
def info():
    """
    Return 200 as default
    """
    return 'ok', 200


@eureka_bp.route('/health')
def health():
    """
    Return 200 as default
    """
    return jsonify({'status': 'UP'}), 200


class Eureka(object):
    def __init__(self, app=None, **kwargs):
        self.kwargs = kwargs if kwargs else {}
        self.app = None
        self.app_list = {}

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        if not hasattr(app, 'eureka'):
            app.eureka = self
        if 'eureka' in app.extensions:
            raise RuntimeError('Flask application already initialized')
        app.register_blueprint(eureka_bp)
        self.register_service()

    def register_service(self, name=None, **kwargs):
        name = self.app.config.get('SERVICE_NAME', name)
        eureka_url = self.app.config.get('EUREKA_SERVICE_URL', None)
        heartbeat_interval = self.app.config.get('EUREKA_HEARTBEAT', None)
        port = self.app.config.get('EUREKA_INSTANCE_PORT', 5000)
        ip_address = self.app.config.get('IP_ADDRESS', None)
        get_ip_cmd = self.app.config.get('GET_IP_CMD', None)
        fetch_registry = self.app.config.get('FETCH_REGISTRY', False)
        eureka_client = EurekaClient(name=name,
                                     eureka_url=eureka_url,
                                     ip_address=ip_address,
                                     port=port,
                                     heartbeat_interval=heartbeat_interval,
                                     get_ip_cmd=get_ip_cmd)
        self.other_apps = eureka_client.other_apps
        eureka_client.star()  # 注册到eureka
        if fetch_registry:
            eureka_client.star_fetch_registry()  # 获取eureka上的服务
