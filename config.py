# eureka配置

# 注册到eureka的服务名称
SERVICE_NAME = "py-example"

# eureka注册服务中心地址
EUREKA_SERVICE_URL = 'http://eureka.example.com'

# 发送心跳/查询其他服务状态 的频率
EUREKA_HEARTBEAT = 30

# 服务端口
EUREKA_INSTANCE_PORT = 5000

# 本地ip
IP_ADDRESS = '127.0.0.1'  # 本地ip，注册到eureka服务中心，置空则根据GET_IP_CMD自动获取本地ip
# 获取本地ip的命令
GET_IP_CMD = "ifconfig eth0 | grep 'inet' | grep -v inet6 | awk '{ print $2 }'"

# 是否开启发现其他服务
FETCH_REGISTRY = True
