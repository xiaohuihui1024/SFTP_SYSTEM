#!C:\Anaconda\python.exe
# -*- coding: utf-8 -*-
import socket
import ssl
# from transitions.extensions.factory import HierarchicalGraphMachine as Machine
from transitions.extensions import HierarchicalMachine as Machine
from transitions.extensions.nesting import NestedState
from common.settings import *
from common.utils import *
from common.sftp_msg import *
import getpass
import json
# Machine.hierarchical_machine_attributes['ranksep'] = '0.3'  # shorter edges
# Machine.hierarchical_machine_attributes['fontname'] = "Inconsolata, Consolas"  # "Microsoft YaHei"


class STFP_Client(Machine):
    def __init__(self, server_uri: tuple = None, ssl_mode=False, cert_path=CERT_PATH):
        Machine.__init__(self, states=STATES, initial="INIT", **extra_args)
        self.__machine_init()  # 配置状态机
        return
        # socket初始化
        self.raw_sock = socket.create_connection(server_uri)
        self.work_sock = None
        if ssl_mode:
            print('使用SSL模式加密传输')
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.context.load_verify_locations(cert_path)
            self.work_sock = self.context.wrap_socket(self.raw_sock, server_hostname=server_uri[0])
        else:
            print('不使用SSL')
            self.work_sock = self.raw_sock

    def __machine_init(self):
        """
        状态机初始化
        主要工作：
        1. 添加 transitions
        2. 输出模型
        """
        self.add_transitions([
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
        ])
        # 图像设置
        # self.style_attributes['edge']["default"]["fontname"] = "Microsoft YaHei"
        # self.get_graph().draw('SFTP_Machine.pdf', prog='dot')   # 输出当前状态机模型

    def reqSignUp(self):
        """
        请求注册逻辑实现
        状态转换：Init ↦ SignUpSuccess (if return True)
        """
        # 获取用户输入
        usr_name = input('>>>username:')
        passwd = getpass.getpass('>>>password:')
        # print(usr_name, passwd)

        # 组装SignUp数据包
        signUpMsg = json.dumps({
            "username": usr_name,
            "password": passwd
        })
        pkg = sftp_msg(pkg_type.SignUp, 1, signUpMsg).pack()
        try:
            # 发送SignUp数据包
            nSent = self.work_sock.send(pkg)
            print(f"发送字节数:{nSent}")
            # 接收返回的数据包
            ret_pkg = sftp_msg(bytes_data=self.work_sock.recv(BUFFER_SIZE))
            assert ret_pkg.ptype == pkg_type.SignUp
            # TODO:根据包内容返回 True or False
            print(ret_pkg)

        except ConnectionResetError as e:
            print('服务器掉线，注册失败')
            return False

    def reqSignIn(self):
        return True

    # 控制台界面
    def work(self):
        """
        以状态机为核心，进入循环过程
        1. 显示当前状态，2. 列出可以选择的 状态转换(功能)
        选择对应的 状态转换(功能) 编号，即可 "尝试" 进行状态转换
        转换过程 设定 回调函数，完成相应的逻辑功能
        """
        print('Welcome SFTP System')    # 打印欢迎语
        while True:
            print(f"\033[0;32mCurrent State\033[0m: \033[1;32m{self.state}\033[0m")  # 1. 显示当前状态
            options = []  # 获取当前可以进行的操作
            extra = []
            if isinstance(self.state, list):  # 并行状态的情况
                # 需求：parent和子状态 的 triggers 区分开, 并且编号要合理
                # 解决：设置附加输出
                parent_state = self.state[0].split(NestedState.separator)[0]
                parent_triggers = self.get_triggers(parent_state)
                options += parent_triggers
                extra += [f' --- [{parent_state}]'] * len(parent_triggers)
                for sub_state in self.state:
                    sub_state_triggers = list_sub(self.get_triggers(sub_state), parent_triggers)
                    options += sub_state_triggers
                    extra += [f' --- [{sub_state}]'] * len(sub_state_triggers)
            else:
                options = self.get_triggers(self.state)
            # 2. 列出可以选择的 状态转换(功能)
            print_msg('\033[0;33mChoose your select\033[0m', options, extra)
            try:
                usr_input = int(input('\nPlease input the Client Command:\n'))  # 获取用户选择
                print(f'you choose {usr_input}:{options[usr_input]}\n')
                self.trigger(options[usr_input])    # 触发 transition，尝试状态转换
                # getattr(self, options[usr_input])()
            except IndexError:
                print('指令编号范围错误')
                continue
            except ValueError:
                print('请输入指令编号')
                continue


if __name__ == '__main__':
    my_client = STFP_Client(SERVER_URI, True)
    my_client.work()
