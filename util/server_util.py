"""
服务器工具包
"""
from common.sftp_msg import *
from functools import update_wrapper
from types import MappingProxyType
from typing import Hashable, Callable, Union
from util.mysql_helper import MySQLHelper
from util.server_settings import SERVER_HOST
import json
import hashlib
from binascii import a2b_hex
import os

conn = MySQLHelper('FQhL&!24%)Aq', 'sftp_db', host=SERVER_HOST)
if conn is None:
    print("数据库连接失败")


def remove_old_token(token: str):
    return conn.delete('session', {'token': token})


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
    pass


@deal_pkg.register((pkg_type.SignUp.value, 0))  # 注：对枚举兼容性不好，需要添加.value
def _(case, data: dict, handler_obj=None):
    """
    处理 客户端 请求注册账号
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
        return sftp_msg(pkg_type.SignUp, 1, json.dumps({"result": "success"})).pack()
    else:
        print("服务器错误")
        return sftp_msg(pkg_type.SignUp, 3, json.dumps({"result": "500"})).pack()


@deal_pkg.register((pkg_type.SignIn.value, 0))
def _(case, data: dict, handler_obj=None):
    """
    处理 客户端 请求登录
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















