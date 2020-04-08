#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : xiaohuihui
# @File    : sftp_msg.py
# @description: 传输协议——控制数据包格式
from enum import IntEnum, unique
import struct


@unique
class pkg_type(IntEnum):
    SignUp = 1
    SignIn = 2
    SignOut = 3
    FILE_DOWNLD = 4
    FILE_UPLD = 5
    SHOW_LIST = 6


# 控制消息
class sftp_msg(object):
    def __init__(self, ptype: pkg_type, ack: int, msg: str = "", bytes_data=None):
        if bytes_data:
            self.ptype, self.ack, self.length, self.msg = sftp_msg.unpack(pkg_msg)
        self.ptype = ptype
        self.ack = ack
        self.msg = msg.encode()
        # 消息长度
        self.length = len(msg)

    def pack(self):
        # 数据包打包
        return struct.pack('BBH{len}s'.format(len=self.length),
                           self.ptype, self.ack, self.length, self.msg)

    def __str__(self):
        return str({
            ptype: self.ptype,
            ack: self.ack,
            length: self.length,
            msg: self.msg,
        })

    @staticmethod
    def unpack(sftp_msg_pkg: bytes):
        # 数据包解包
        length = struct.unpack('H', sftp_msg_pkg[2:4])[0]
        return struct.unpack('@BB2s{len}s'.format(len=length), sftp_msg_pkg)
# 文件数据


if __name__ == '__main__':
    # msg = sftp_msg(pkg_type.FILE_UPLD, 6, "helloworld")
    msg = sftp_msg(pkg_type.SignUp, 1)
    pkg_msg = msg.pack()
    print(pkg_msg)
    ptype, ack, length, msg = sftp_msg.unpack(pkg_msg)
    print(ptype, ack, length, msg)


