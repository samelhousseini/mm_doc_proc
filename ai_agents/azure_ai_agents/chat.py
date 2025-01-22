import os
import requests
from dotenv import load_dotenv
load_dotenv()

import chainlit as cl
from chainlit import run_sync
from chainlit import make_async


from orchestrator import *
orchestrator = Orchestrator()


# Instructions to run
# chainlit run chat.py

@cl.on_chat_start
async def start():
    pass


@cl.on_message
async def main(message: cl.Message):
    message_content = message.content.strip().lower()
    elements = []

    answer = await orchestrator.chat(message_content)
    await cl.Message(content=answer, elements = elements).send()