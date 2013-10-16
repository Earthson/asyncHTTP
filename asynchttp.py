#!/usr/bin/env python

conn_limit = 5000

from tornado import httpclient
from http.client import HTTPMessage, HTTPResponse

from http.cookiejar import MozillaCookieJar, DefaultCookiePolicy
import urllib.request

from tornado.ioloop import IOLoop
io_loop = IOLoop.instance()

class TmpResponse(object):
    '''hacking with info method'''
    def __init__(self, info):
        self._info = info

    def info(self):
        return self._info


def nothing():
    pass


def client_gen(http_client, task_start=nothing, task_end=nothing):
    def sender_gen(cj, proxy=None):
        #cj.save(ignore_discard=True, ignore_expires=True)
        try:
            #try load file
            cj.load(ignore_discard=True, ignore_expires=True)
        except:
            #File May not exist
            pass
        def sender(url, callback):
            oreq = urllib.request.Request(url)
            proxy_host=None if proxy is None else proxy[0]
            proxy_port=None if proxy is None else proxy[1]
            req = httpclient.HTTPRequest(url, request_timeout=5.0)
            cj.add_cookie_header(oreq)
            req.headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.57 Safari/537.36",
            }
            req.headers.update(oreq.header_items())
            def callback_gen(callback):
                def func(response):
                    try:
                        responseinfo = HTTPMessage()
                        for k, v in response.headers.items():
                            responseinfo[k] = v
                        tmpresponse = TmpResponse(responseinfo)
                        cj.extract_cookies(tmpresponse, oreq)
                        callback(response)
                        #cj.save(ignore_discard=True, ignore_expires=True)

                        #tell taskmanager that the task have been done
                    finally:
                        task_end()
                return func
            #try to start task, taskmanager may block here for limiting connection:)
            task_start()
            http_client.fetch(req, callback=callback_gen(callback))
        return sender
    return sender_gen



import threading
import time

__conn_count = 0
__conn_lock = threading.Lock()

def tasker_start(limit=1000):
    def func():
        global __conn_count, __conn_lock
        while __conn_count > limit:
            time.sleep(1)
        __conn_lock.acquire()
        __conn_count += 1
        __conn_lock.release()
    return func


def tasker_end():
    def func():
        __conn_lock.acquire()
        __conn_count -= 1
        __conn_lock.release()
    return func


from queue import Queue

task_q = Queue()

def task_alloc():
    while True:
        x = task_q.get()
        x[0](*x[1:])
        


def start_task_alloc():
    task_th = threading.Thread(target=task_alloc)
    task_th.daemon = True
    task_th.start() 


def add_task(sender, url, callback):
    task_q.put(sender, url, callback)


def reg_task(sender, url):
    def func(callback):
        def ifunc(response):
            ans = callback(response)
            if ans is not None:
                for e in ans:
                    add_task(sender, *e)
        add_task(sender, url, ifunc)
        return ifunc
    return func

start_task_alloc()
