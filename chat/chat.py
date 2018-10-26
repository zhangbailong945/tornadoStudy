import tornado.httpserver
import tornado.web
import tornado.ioloop
import tornado.options
import os.path
import asyncio
import tornado.escape
import tornado.locks
import uuid


from tornado.options import define,options
define("port",default=8888,type=int,help="run localhost:8888")
define("debug",default=True,help="starting debug")

class MessageBuffer(object):

    def __init__(self):
        self.cond=tornado.locks.Condition()
        self.cache=[]
        self.cache_size=200
    

    def get_messages_since(self,cursor):
        results=[]
        for msg in reversed(self.cache):
            if msg['id']==cursor:
                break
            results.append(msg)
        results.reverse()
        return results
    
    def add_message(self,message):
        self.cache.append(message)
        if len(self.cache)>self.cache_size:
            self.cache=self.cache[-self.cache_size:]
        self.cond.notify_all()
            


global_message_buffer = MessageBuffer()

class MessageNewHandler(tornado.web.RequestHandler):
     
    #发送消息
    def post(self):
        message={
            "id":str(uuid.uuid4()),
            "body":self.get_argument('body'),
        }
        message['html']=tornado.escape.to_unicode(
            self.render_string("message.html",message=message)
        )
        if self.get_argument("next",None):
            self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        global_message_buffer.add_message(message)


class IndexHandler(tornado.web.RequestHandler):

    def get(self):
        self.render("index.html",messages=global_message_buffer.cache)


class MessageUpdatesHandler(tornado.web.RequestHandler):
    """Long-polling request for new messages.
    Waits until new messages are available before returning anything.
    """
    async def post(self):
        cursor = self.get_argument("cursor", None)
        messages = global_message_buffer.get_messages_since(cursor)
        while not messages:
            # Save the Future returned here so we can cancel it in
            # on_connection_close.
            self.wait_future = global_message_buffer.cond.wait()
            try:
                await self.wait_future
            except asyncio.CancelledError:
                return
            messages = global_message_buffer.get_messages_since(cursor)
        if self.request.connection.stream.closed():
            return
        self.write(dict(messages=messages))

    def on_connection_close(self):
        self.wait_future.cancel()       


class Application(tornado.web.Application):

    def __init__(self):
        handlers=[
            (r"/",IndexHandler),
            (r"/a/message/new",MessageNewHandler),
            (r"/a/message/updates",MessageUpdatesHandler),
        ]
        settings=dict(
            cookie_secret="ZHANGBAILONG",
            template_path=os.path.join(os.path.dirname(__file__),"templates"),
            static_path=os.path.join(os.path.dirname(__file__),"static"),
            xsrf_cookies=True,
            debug=options.debug,
        )
        tornado.web.Application.__init__(self,handlers=handlers,**settings)


if __name__=="__main__":
    tornado.options.parse_command_line()
    http_server=tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
