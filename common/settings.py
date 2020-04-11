#!/usr/bin/env python
# -*- coding: utf-8 -*-
from transitions.extensions.nesting import NestedState
from socketserver import ThreadingTCPServer
# SERVER_HOST = '127.0.0.1'
SERVER_HOST = 'xiaohuihui.test.com'
SERVER_PORT = 22222
CERT_PATH = 'common/server.crt'
SERVER_URI = (SERVER_HOST, SERVER_PORT)
BUFFER_SIZE = 1024
FILE_BUFFER_SIZE = 10240
LOCAL_DIR = "./MY_FILES/"


NestedState.separator = '↦'  # TODO: bug for 0.8.0
# extra_args = dict(auto_transitions=False, use_pygraphviz=False, show_conditions=False, show_state_attributes=True,)
extra_args = dict(auto_transitions=False,)




