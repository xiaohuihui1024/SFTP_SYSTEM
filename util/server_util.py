"""
服务器工具包
"""
from common.sftp_msg import *
from functools import update_wrapper
from types import MappingProxyType
from typing import Hashable, Callable, Union
from util.mysql_helper import MySQLHelper
from util.server_settings import *
import json
import hashlib
from binascii import a2b_hex
import os
import platform
import ctypes
from transitions.extensions import HierarchicalMachine  # 仅供代码提示用，可以删除
from transitions.extensions.nesting import NestedState
NestedState.separator = '↦'
extra_args = dict(auto_transitions=False, use_pygraphviz=False, show_conditions=False, show_state_attributes=True,)

conn = MySQLHelper('FQhL&!24%)Aq', 'sftp_db', host=SERVER_HOST)
if conn is None:
    print("数据库连接失败")


def remove_old_token(token: str):
    return conn.delete('session', {'token': token})


def check_token(token: str):
    results, count = conn.query('session', cond={"token": token})
    # print(results, count)
    return results[0]["username"] if count else None


def get_free_space_mb(folder):
    """ Return folder/drive free space (in bytes)
    """
    if platform.system() == 'Windows':
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(folder), None, None, ctypes.pointer(free_bytes))
        return free_bytes.value  # /1024/1024/1024
    else:
        st = os.statvfs(folder)
        return st.f_bavail * st.f_frsize  # /1024/1024/1024

# server端FSM设计：仅做合法性判断。
# 可以拓展两层映射，用 FSM 驱动 Handler状态
STATES = ["INIT",
          "EXIT",
          {
              "name": "Running",
              "children": [  # parallel
                  {
                      "name": "UP_MODE",
                      "children": ["INIT", "Prepare_1", "ing_2", "Down_33"]  # 上传文件子 协议状态
                  },
                  {
                      "name": "DOWN_MODE",
                      "children": ["INIT", "Prepare", "ing", "Down"]  # 下载文件子 协议状态
                  }]
          }]
TRANSITIONS = [
    {"trigger": "resSignUp", "source": "INIT", "dest": "="},        # 注册
    {"trigger": "resSignIn", "source": "INIT", "dest": "Running"},  # 登录
    {"trigger": "resSignOut", "source": "Running", "dest": "INIT"},  # 登出
    {"trigger": "resDir", "source": "Running", "dest": None},       # 展示文件列表
    #{"trigger": "", "source": "", "dest": ""},  #
    #{"trigger": "", "source": "", "dest": ""},  #
    #{"trigger": "", "source": "", "dest": ""},  #
    #{"trigger": "", "source": "", "dest": ""},  #
    #{"trigger": "", "source": "", "dest": ""},  #

]


def specificdispatch(key: Union[int, str] = 0) -> Callable:
    """
    实现简易函数重载的 装饰器，参考 PEP443
    用法：
    @specificdispatch(key=xxx) 装饰一个函数
    """

    def decorate(func: Callable) -> Callable:
        registry = {}

        def dispatch(key: Hashable) -> Callable:
            """
            Runs the dispatch algorithm to return the best available implementation
            for the given *key* registered on *generic_func*.
            """
            try:
                impl = registry[key]
            except KeyError:
                impl = registry[object]
            return impl

        def register(key: Hashable, func: Callable=None) -> Callable:
            """
            Registers a new implementation for the given *key* on a *generic_func*.
            """
            if func is None:
                return lambda f: register(key, f)

            registry[key] = func
            return func

        def wrapper_index(*args, **kw):
            return dispatch(args[key])(*args, **kw)

        def wrapper_keyword(*args, **kw):
            return dispatch(kw[key])(*args, **kw)

        registry[object] = func
        if isinstance(key, int):
            wrapper = wrapper_index
        elif isinstance(key, str):
            wrapper = wrapper_keyword
        else:
            raise KeyError('The key must be int or str')
        wrapper.register = register
        wrapper.dispatch = dispatch
        wrapper.registry = MappingProxyType(registry)
        update_wrapper(wrapper, func)

        return wrapper

    return decorate


@specificdispatch(key="case")
def deal_pkg(case: tuple, **kwargs):
    """
    没有定义case的情况会转到这里
    """
    print("invalid case：", case)
    print(kwargs)


@deal_pkg.register((pkg_type.SignUp.value, 0))  # 注：对枚举兼容性不好，需要添加.value
def _(case, data: dict, handler_obj: Union[HierarchicalMachine] = None):
    """
    处理 客户端 请求注册账号 SignUp
    """
    user_info = json.loads(data)
    retdata, count = conn.query('user', cond={"username": user_info["name"]})
    if count is 1:  # 重名返回FALSE
        return sftp_msg(pkg_type.SignUp, 2,
                        json.dumps({"result": f"{user_info['name']} has been registered"})).pack()
    elif count > 1:
        print("数据库中存在多个重名用户错误，请检查")
        return sftp_msg(pkg_type.SignUp, 2,
                        json.dumps({"result": f"{user_info['name']} has been registered"})).pack()
    user_salt = os.urandom(20)  # 随机生成一个用户盐
    insert_usr_info = {
        'username': user_info["name"],
        'salt': user_salt.hex(),
        'password': hashlib.sha1(user_info['pwd'].encode() + user_salt).hexdigest()
    }
    if conn.insert("user", insert_usr_info):
        os.makedirs(FILE_DIR + user_info["name"], exist_ok=True)
        return sftp_msg(pkg_type.SignUp, 1, json.dumps({"result": "success"})).pack()
    else:
        print("服务器错误")
        return sftp_msg(pkg_type.SignUp, 3, json.dumps({"result": "500"})).pack()


@deal_pkg.register((pkg_type.SignIn.value, 0))
def _(case, data: dict, handler_obj=None):
    """
    处理 客户端 请求登录 SignIn
    """
    user_info = json.loads(data)
    retdata, count = conn.query('user', cond={"username": user_info["name"]})
    if count > 0:  # 已经注册的情况, 继续检查密码
        if retdata[0]["password"] == hashlib.sha1(user_info['pwd'].encode() + a2b_hex(retdata[0]['salt'])).hexdigest():
            # 生成token并发送
            token = os.urandom(20).hex()
            conn.insert('session', {'username': retdata[0]["username"], 'token': token})
            handler_obj.token = token
            return sftp_msg(pkg_type.SignIn, 1, json.dumps({"result": "success", "token": token})).pack()
    else:
        print('用户未注册')
    # 未注册、密码错误统一输出，防止通过接口试探用户名
    return sftp_msg(pkg_type.SignIn, 2, json.dumps({"result": "username or pwd error"})).pack()


@deal_pkg.register((pkg_type.SignOut, 0))
def _(case, data: dict, handler_obj=None):
    """
    处理客户端退出登录 SignOut
    """
    out_token = json.loads(data)['token']
    remove_old_token(out_token)
    return None


@deal_pkg.register((pkg_type.FILE_UPLD.value, 0))
@deal_pkg.register((pkg_type.FILE_UPLD.value, 1))
def _(case, data: dict, handler_obj=None):
    """
    处理客户端 上传文件 请求
    :return: 拒绝 or 做好准备
    """
    file_info = json.loads(data)
    usr_name = check_token(file_info["token"])
    if usr_name is None:
        # 登录状态异常
        return sftp_msg(pkg_type.FILE_UPLD, 8, json.dumps({"result": "Invalid user"})).pack()
    if file_info["filesize"] > get_free_space_mb(FILE_DIR):
        # 磁盘空间不足
        return sftp_msg(pkg_type.FILE_UPLD, 4, json.dumps({"result": "Insufficient disk space"})).pack()
    FILE_FULL_PATH = f"{FILE_DIR}{usr_name}/{file_info['filename']}"
    if os.path.exists(FILE_FULL_PATH):
        # 存在重名文件
        if case[1] == 1:
            # 覆盖型： 删除文件
            os.remove(FILE_FULL_PATH)
        else:
            # 非覆盖性：提示存在重名
            return sftp_msg(pkg_type.FILE_UPLD, 3, json.dumps({"result": "duplication of filename"})).pack()
    else:
        pass
    # data_sock 开始监听
    if handler_obj.data_client_sock is None:
        handler_obj.data_sock.listen(1)
    # 保存文件信息
    handler_obj.cur_file_info = (file_info["filename"], file_info["filesize"])
    # 返回 接收上传请求数据包
    return sftp_msg(pkg_type.FILE_UPLD, 2, json.dumps({"result": "can!", "port": SERVER_DATA_PORT})).pack()


@deal_pkg.register((pkg_type.FILE_UPLD.value, 5))
def _(case, data: dict, handler_obj=None):
    """
    接收 上传的文件
    :return:
    """
    usr_token = json.loads(data)
    usr_name = check_token(usr_token["token"])
    if usr_name is None:
        # 登录状态异常
        return sftp_msg(pkg_type.FILE_UPLD, 8, json.dumps({"result": "Invalid user"})).pack()
    # data_client_sock 建立SSL
    if handler_obj.data_client_sock is None:
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        context.load_cert_chain(certfile=CERT_PATH, keyfile=KEY_PATH)
        handler_obj.data_client_sock, addr = handler_obj.data_sock.accept()
        print("数据套接字连接地址: %s" % str(addr))
        handler_obj.data_client_sock = context.wrap_socket(handler_obj.data_client_sock, server_side=True)
    # 接收文件
    cur_size = 0
    FILE_FULL_PATH = f"{FILE_DIR}{usr_name}/{handler_obj.cur_file_info[0]}"
    with open(FILE_FULL_PATH, 'wb') as f:
        while cur_size < handler_obj.cur_file_info[1]:
            """
            大文件传输有个坑：
            (1) 调用recv有数据就接收，没有数据就会等待
            (2) 每次实际接收的数据长度未知; 
            (3) 因此需要提前预知数据大小，判断接收完成
            """
            file_bytes = handler_obj.data_client_sock.recv(FILE_BUFFER_SIZE)
            f.write(file_bytes)  # 将 recv 收到的数据写入文件
            cur_size = f.tell()  # 当前文件指针位置, 即当前成功接收了多少字节数据
            # print(f"{cur_size}/{handler_obj.cur_file_info[1]} ====> {cur_size/handler_obj.cur_file_info[1]*100}%")
        # 文件接收完毕
        f.close()
    # 重置相关变量
    handler_obj.cur_file_info = None        # 文件信息
    handler_obj.data_client_sock.close()    # 与客户端的socket连接
    del handler_obj.data_client_sock
    handler_obj.data_client_sock = None
    # 发送 文件传输完毕
    return sftp_msg(pkg_type.FILE_UPLD, 7, json.dumps({"result": "accept over"})).pack()


@deal_pkg.register((pkg_type.SHOW_LIST.value, 0))
def _(case, data: dict, handler_obj=None):
    usr_token = json.loads(data)
    usr_name = check_token(usr_token["token"])
    if usr_name is None:
        # 登录状态异常
        return sftp_msg(pkg_type.SHOW_LIST, 3, json.dumps({"result": "Invalid user"})).pack()
    try:
        usr_filelist = os.listdir(FILE_DIR+usr_name)
        return sftp_msg(pkg_type.SHOW_LIST, 1, json.dumps({"result": usr_filelist})).pack()
    except OSError:
        return sftp_msg(pkg_type.SHOW_LIST, 2, json.dumps({"result": "OSError"})).pack()













