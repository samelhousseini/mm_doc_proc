import os
from dotenv import load_dotenv
load_dotenv()


AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '')

AZURE_OPENAI_RESOURCE = os.environ.get('AZURE_OPENAI_RESOURCE', '')
AZURE_OPENAI_KEY = os.environ.get('AZURE_OPENAI_KEY', "2024-02-29-preview")
AZURE_OPENAI_MODEL = os.environ.get('AZURE_OPENAI_MODEL', '')

AZURE_OPENAI_RESOURCE_O1 = os.environ.get('AZURE_OPENAI_RESOURCE_O1', '')
AZURE_OPENAI_KEY_O1 = os.environ.get('AZURE_OPENAI_KEY_O1', '')
AZURE_OPENAI_MODEL_O1 = os.environ.get('AZURE_OPENAI_MODEL_O1', '')

AZURE_OPENAI_RESOURCE_O1_MINI = os.environ.get('AZURE_OPENAI_RESOURCE_O1_MINI', '')
AZURE_OPENAI_KEY_O1_MINI = os.environ.get('AZURE_OPENAI_KEY_O1_MINI', '')
AZURE_OPENAI_MODEL_O1_MINI = os.environ.get('AZURE_OPENAI_MODEL_O1_MINI', '')

TENACITY_STOP_AFTER_DELAY = 300
TENACITY_TIMEOUT = 300

AZURE_AI_SEARCH_SERVICE_NAME = os.environ.get('AZURE_AI_SEARCH_SERVICE_NAME', '')
AZURE_AI_SEARCH_API_KEY = os.environ.get('AZURE_AI_SEARCH_API_KEY', '')