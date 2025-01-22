from fastapi import FastAPI
from chainlit.utils import mount_chainlit
from chainlit.context import init_http_context
import chainlit as cl


# Command to start is uvicorn main:app --host 127.0.0.1 --port 80
app = FastAPI()

mount_chainlit(app=app, target="chat.py", path="")