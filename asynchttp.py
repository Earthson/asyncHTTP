#!/usr/bin/env python

import sys
import email
import types
from http.client import HTTPMessage, HTTPResponse
from http.cookiejar import MozillaCookieJar, DefaultCookiePolicy
import urllib.request
from urllib.parse import urlparse

from tornado import httpclient
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
io_loop = IOLoop.instance()


from itertools import count

pass_cnt = count()
fail_cnt = count()
from . import utils
bg_timmer = utils.stimmer()


#redirect black list. prevent random HTTP hijacking
host_black_list = [
        'bestpay.com.cn',
        ]

def use_curl():
    AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")


def req_gen(url, referer='', **kwargs):
    ug = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.66 Safari/537.36'
    if url[:4] != 'http':
        thost = urlparse(referer)
        parent = '/'.join(thost.path.split('/')[:-1])
        if url[:2] == '//':
            url = thost.scheme+':'+url
        elif url[0] == '/':
            url = thost.scheme+"://"+thost.hostname+url
        elif url[0] == '?':
            url = thost.scheme+"://"+thost.hostname+thost.path+url
        else:
            url = thost.scheme+"://"+thost.hostname+parent+'/'+url
    headers = {
        #"Accept":"*/*",
        #"Accept-Language":"en-US,en;q=0.8",
        "Host":urlparse(url).hostname,
        "Referer":referer,
        "Cache-Control":"no-cache",
        "Connection":"keep-alive",
        #"User-Agent":'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.57 Safari/537.36',
        }
    ans = {
            "url":url,
            "headers":headers,
            "user_agent":ug,
            "request_timeout":10,
            "follow_redirects":False,
            "max_redirects":25,
            "use_gzip":True,
        }
    ans.update(**kwargs)
    return ans


class TmpResponse(object):
    '''hacking with info method'''
    def __init__(self, info):
        self._info = info

    def info(self):
        return self._info



def nothing(*args, **kwargs):
    pass

__conn_count = 0

def client_gen(http_client, limit):
    def sender_gen(cj, timeout=8):
        #cj.save(ignore_discard=True, ignore_expires=True)
        try:
            #try load file
            cj.load(ignore_discard=True, ignore_expires=True)
        except:
            #File May not exist
            pass
        def sender(req, callback):
            if isinstance(req, str):
                try:
                    req = httpclient.HTTPRequest(**req_gen(req, ''))
                except Exception as e:
                    print('@url_generate_error:', e, file=sys.stderr)
                    return
            elif isinstance(req, dict):
                req = httpclient.HTTPRequest(**req)
            oreq = urllib.request.Request(req.url)
            cj.add_cookie_header(oreq)
            req.headers.update(oreq.header_items())
            #print(req.headers)
            def callback_gen(callback):
                def func(response):
                    try:
                        #tell taskmanager that the task have been done
                        global __conn_count
                        __conn_count -= 1
                        responseinfo = email.parser.Parser(HTTPMessage).parsestr('\n'.join(':'.join(e) for e in response.headers.get_all()))
                        tmpresponse = TmpResponse(responseinfo)
                        cj.extract_cookies(tmpresponse, oreq)
                        #print(cj)
                        redirect_wrap(callback, redirect_callback=func, sender=sender)(response)
                    finally:
                        print("@finish_request:", response.request.url, file=sys.stderr)
                return func
            #try to start task, taskmanager may block here for limiting connection:)

            def tofetch():
                global __conn_count
                if __conn_count < limit:
                    __conn_count += 1
                    http_client.fetch(req, callback=callback_gen(callback))
                else:
                    io_loop.add_timeout(io_loop.time()+0.1, tofetch)
            io_loop.add_callback((lambda :io_loop.add_timeout(io_loop.time(), tofetch())))
        return sender
    return sender_gen



from random import choice
from functools import partial
from . import utils


#magic below, do not change anything. I don't think you can hold on.

def redirect_wrap(func, redirect_callback, sender=None):
    '''it's not enough infomation for redirect to be done.
    so you have to pass an full callback function as redirect_callback().
    it is a magic trick, this call make recursive to be lazy. without this call, you may have unlimited recursive error
    '''
    def ifunc(response, *args, **kwargs):
        curl = response.request.url
        relurl = response.effective_url
        rhost = urlparse(relurl).hostname
        for each in host_black_list:
            if each in rhost:
                print('@url_in_black_list:', relurl, file=sys.stderr)
                response.code = 599
                response.error = Exception('url_in_black_list')
                break
        if response.code in (301, 302):
            req = req_gen(response.headers['Location'], relurl)
            print('@redirect: %s => %s' % (relurl, req['url']), file=sys.stderr)
            if sender is None:
                choice(origin_senders)(req, redirect_callback)
            else:
                sender(req, redirect_callback)
            return
        return func(response, *args, **kwargs)
    return ifunc


def init_wrap(func):
    def ifunc(response, *args):
        if response.code != 200:
            print("@HTTPError: Code:", response.code, response.effective_url, file=sys.stderr)
            print("@time_info: \n#fail: %s \n#time: %s" % (next(fail_cnt), bg_timmer()))
            response.rethrow()
            return
        print("@time_info: \n#pass: %s \n#time: %s" % (next(fail_cnt), bg_timmer()))
        charset = utils.charset_from_response(response)
        response.ubody = utils.try_decode(response.body, charset)
        return func(response, *args)
    return ifunc

from traceback import format_exc

def ahttp_gen(mgr, senders):
    call_mapper = dict()
    @mgr.reg_proc('asynchttp')
    def aproc(tasktype, args, kwargs, key, **extra_info):
        sender = choice(senders)
        if kwargs['calltype'] not in call_mapper:
            print('@Unknown_Task:', tasktype, args, kwargs, file=sys.stderr)
            mgr.fail(key)
            return
        tocall = call_mapper[kwargs['calltype']]
        def ack_call(*args, **kwargs):
            #try ignore all arguments
            mgr.ack(key)
            print("@finish", file=sys.stderr)
        def fail_call(*args, **kwargs):
            #try ignore all arguments
            print("@error_trace_back", format_exc(), file=sys.stderr)
            mgr.fail(key)
        icall = tocall(sender, callback=ack_call, err_callback=fail_call)
        for req in args:
            sender(req, icall)

    def call_reg(calltype):
        def regger(func):
            def ifunc(sender, callback, err_callback):
                return recgen.rec_gen(init_wrap(func), callback=callback, err_callback=err_callback)
            call_mapper[calltype] = ifunc
            return func
        return regger

    from . import recgen
    def call_reg_with_sender(calltype):
        def regger(func):
            def ifunc(sender, callback, err_callback):
                return recgen.rec_gen(init_wrap(partial(func, sender=sender)), callback=callback, err_callback=err_callback)
            call_mapper[calltype] = ifunc
            return func
        return regger

    return call_reg, call_reg_with_sender


def task_adder(mgr):
    def task_add(calltype, req, key=None):
        mgr.add(tasktype='asynchttp', args=(req,), kwargs={'calltype':calltype}, key=key)
    return task_add


class HTTPReg(object):
    def __init__(self, mgr, senders):
        self.mgr = mgr
        self.senders = senders
        self.reg, self.reg_with_sender = ahttp_gen(mgr, senders)
        self.add = task_adder(mgr)


def get_senders(mac_cnt=1, extra_cookie=None, **kwargs):
    #fnames = ["cookies/%s.cookie" % i for i in range(mac_cnt)]
    #maccookies = [MozillaCookieJar(e, policy=DefaultCookiePolicy(rfc2965=True)) for e in fnames]
    #maccookies = [MozillaCookieJar(e) for e in fnames]
    maccookies = [MozillaCookieJar() for i in range(mac_cnt)]
    if extra_cookie is not None:
        for each in maccookies:
            each.set_cookie(extra_cookie)
    async_client = client_gen(httpclient.AsyncHTTPClient(), 40)
    return [async_client(e, **kwargs) for e in maccookies]


origin_senders = get_senders(1)


if __name__ == "__main__":
    sender = get_senders()[0]
    sender('http://www.google.com', lambda x:print(x))
    io_loop.start()
