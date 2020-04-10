#!/usr/bin/env python
# -*- coding: utf-8 -*-
# from enum import Enum, unique, auto
# from transitions.core import Enum


def print_msg(title, options, extra=None):
    print(title)
    len_ = len(options)
    for i in range(len_):
        if extra:
            assert len_ == len(extra)
            print(f"\033[0;33m{i}:\033[0m \033[36m{options[i]}\033[0m\033[1;32m{extra[i]}\033[0m")
        else:
            print(f"\033[0;33m{i}:\033[0m \033[36m{options[i]}\033[0m")
    # for index, item in enumerate(options):
    #     if extra:
    #         print(f"\033[0;33m{index}:\033[0m \033[36m{item}\033[0m\033[1;32m{extra}\033[0m")
    #     else:
    #         print(f"\033[0;33m{index}:\033[0m \033[36m{item}\033[0m")


def list_sub(list1: list, list2: list):
    """
    list集合相减，即 list1 - list2
    :return: list1 - list2
    """
    # return list(set(list1) - set(list2))
    return [i for i in list1 if i not in list2]


# Advanced: transitions 0.9.0 发布后可以直接使用嵌套枚举初始化 HSM
# Advanced: 由于枚举在实际使用过程中由较多bug, 觉得不采用枚举表示状态. 如
# 枚举 + parallel + 图 + '↦' 组合起来
# class RunningSubStates(Enum):
#     LS_MODE = 31
#     UP_MODE = 32
#     DOWN_MODE = 33
#
#
# @unique
# class RootStates(Enum):
#     INIT = 0
#     SignUpSuccess = 1
#     # Running = RunningSubStates
#     # Running = [v for v in RunningSubStates]
#     Running = 3

STATES = ["INIT",
          "SignUpSuccess",
          {
              'name': "Running",
              # 'parallel': ["LS_MODE", "UP_MODE", "DOWN_MODE"],
              'children': ["LS_MODE", "UP_MODE", "DOWN_MODE"],
              'initial': "LS_MODE",
           }]


TRANSITIONS = [
    {   # 注册
        'source': "INIT", 'dest': "SignUpSuccess",
        'trigger': 'Try to SignUp',
        'conditions': 'reqSignUp'
    },
    {   # 回滚到Init
        'source': ["SignUpSuccess", "Running"], 'dest': "INIT",
        'trigger': 'Go Back'
    },
    {   # 登录
        'source': "INIT", 'dest': "Running",
        'trigger': 'Try to SignIn',
        'conditions': "reqSignIn"
    },
    {    # 显示云端目录
       'source': 'Running↦LS_MODE', 'dest': None,
       'trigger': "Show Romete Directory",
       'conditions': 'reqRemoteDir'
    },
    {   # 显示本地目录
       'source': 'Running↦LS_MODE', 'dest': None,
       'trigger': "Show Local Directory",
       'conditions': 'reqLocalDir'
    },
    {   # 上传文件
       'source': 'Running↦UP_MODE', 'dest': None,
       'trigger': "Upload files",
       'conditions': 'reqUploadFile'
    },
    {   # 下载文件
       'source': 'Running↦DOWN_MODE', 'dest': None,
       'trigger': "Download files",
       'conditions': 'reqDownloadFile'
    }
]

from functools import update_wrapper
from types import MappingProxyType
from typing import Hashable, Callable, Union




if __name__ == '__main__':
    print(STATES)

