#!/usr/bin/env python
"""
Document Processing Job
This script processes documents uploaded to the Azure Blob Storage container.
It is triggered by events from the Azure Queue.
"""

import os
import json
import uuid
import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
import azure.storage.blob as blob_storage
from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.cosmos import CosmosClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
# from azure.search.documents.models import Vector
import openai
from dotenv import load_dotenv

import asyncio
from azure.servicebus.aio import ServiceBusClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from dotenv import dotenv_values

import sys
sys.path.append("../../")
sys.path.append("../")
sys.path.append(".")

from utils.openai_utils import *
from utils.openai_data_models import *
from storage.azure_blob_storage import AzureBlobStorage
from multimodal_processing_pipeline.configuration_models import ProcessingPipelineConfiguration, CustomProcessingStep
from orchestration.document_ingestion_job import DocumentIngestionJob
from search.search_data_models import AISearchConfig, SearchUnit

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration from environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME", "data")
AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME", "documents")
AZURE_STORAGE_ACCOUNT_ID = os.getenv("AZURE_STORAGE_ACCOUNT_ID")
AZURE_STORAGE_QUEUE_NAME = os.getenv("AZURE_STORAGE_QUEUE_NAME", "document-processing-queue")


AZURE_STORAGE_OUTPUT_CONTAINER_NAME = os.getenv("AZURE_STORAGE_OUTPUT_CONTAINER_NAME", "processed")
STORAGE_QUEUE_NAME = os.getenv("STORAGE_QUEUE_NAME", "doc-process-queue")

# Azure OpenAI Configuration
AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE")
AZURE_OPENAI_KEY_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_KEY_EMBEDDING_LARGE")
AZURE_OPENAI_MODEL_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_MODEL_EMBEDDING_LARGE", "text-embedding-3-large")
AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE = os.getenv("AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE", "2024-12-01-preview")

AZURE_OPENAI_RESOURCE_4O = os.getenv("AZURE_OPENAI_RESOURCE_4O")
AZURE_OPENAI_KEY_4O = os.getenv("AZURE_OPENAI_KEY_4O")
AZURE_OPENAI_MODEL_4O = os.getenv("AZURE_OPENAI_MODEL_4O", "gpt-4o-2")
AZURE_OPENAI_API_VERSION_4O = os.getenv("AZURE_OPENAI_API_VERSION_4O", "2024-12-01-preview")

# Azure AI Search Configuration
AZURE_AI_SEARCH_SERVICE_NAME = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME")
AZURE_AI_SEARCH_API_KEY = os.getenv("AZURE_AI_SEARCH_API_KEY")
AZURE_AI_SEARCH_INDEX_NAME = "document-index"

# Cosmos DB Configuration
COSMOS_URI = os.getenv("COSMOS_URI")

COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME", "KYC")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_CONTAINER_NAME", "Customers")
COSMOS_LOG_CONTAINER = os.getenv("COSMOS_LOG_CONTAINER", "logs")
SERVICE_BUS_NAME = os.getenv("SERVICE_BUS_NAME", "servicebus")
SERVICE_BUS_QUEUE_NAME = os.getenv("SERVICE_BUS_QUEUE_NAME", 'document-processing-queue')
COSMOS_CATEGORYID = os.getenv("COSMOS_CATEGORYID", "categoryId")
COSMOS_CATEGORYID_VALUE = os.getenv("COSMOS_CATEGORYID_VALUE", "documents")

# App Insights for monitoring
APP_INSIGHTS_CONN_STRING = os.getenv("APP_INSIGHTS_CONN_STRING")

fully_qualified_namespace=f"{SERVICE_BUS_NAME}.servicebus.windows.net"
queue_name=SERVICE_BUS_QUEUE_NAME
max_wait_time=5
max_message_count=20
MIN_NUMBER=1
MAX_NUMBER=20
MESSAGE_COUNT=100

debug_prints = True

if debug_prints:
  print("Debug prints enabled.")
  # Print environment variables
  print(f"FULLY_QUALIFIED_NAMESPACE: {fully_qualified_namespace}")
  print(f"QUEUE_NAME: {queue_name}")
  print(f"MAX_MESSAGE_COUNT: {max_message_count}")
  print(f"MAX_WAIT_TIME: {max_wait_time}")
  print(f"MIN_NUMBER: {MIN_NUMBER}")
  print(f"MAX_NUMBER: {MAX_NUMBER}")
  print(f"AZURE_STORAGE_ACCOUNT_NAME: {AZURE_STORAGE_ACCOUNT_NAME}")
  print(f"AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME: {AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME}")
  print(f"AZURE_STORAGE_OUTPUT_CONTAINER_NAME: {AZURE_STORAGE_OUTPUT_CONTAINER_NAME}")
  print(f"STORAGE_QUEUE_NAME: {STORAGE_QUEUE_NAME}")
  print(f"AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE: {AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE}")
  print(f"AZURE_OPENAI_KEY_EMBEDDING_LARGE: {AZURE_OPENAI_KEY_EMBEDDING_LARGE}")
  print(f"AZURE_OPENAI_MODEL_EMBEDDING_LARGE: {AZURE_OPENAI_MODEL_EMBEDDING_LARGE}")
  print(f"AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE: {AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE}")
  print(f"COSMOS_URI: {COSMOS_URI}")
  print(f"COSMOS_DB_NAME: {COSMOS_DB_NAME}")
  print(f"COSMOS_CONTAINER_NAME: {COSMOS_CONTAINER_NAME}")
  print(f"COSMOS_LOG_CONTAINER: {COSMOS_LOG_CONTAINER}")
  print(f"COSMOS_CATEGORYID: {COSMOS_CATEGORYID}")
  print(f"COSMOS_CATEGORYID_VALUE: {COSMOS_CATEGORYID_VALUE}")
  print(f"AZURE_AI_SEARCH_SERVICE_NAME: {AZURE_AI_SEARCH_SERVICE_NAME}")
  print(f"AZURE_AI_SEARCH_API_KEY: {AZURE_AI_SEARCH_API_KEY}")
  print(f"AZURE_AI_SEARCH_INDEX_NAME: {AZURE_AI_SEARCH_INDEX_NAME}")
  print(f"AZURE_OPENAI_RESOURCE_4O: {AZURE_OPENAI_RESOURCE_4O}")
  print(f"AZURE_OPENAI_KEY_4O: {AZURE_OPENAI_KEY_4O}")
  print(f"AZURE_OPENAI_MODEL_4O: {AZURE_OPENAI_MODEL_4O}")
  print(f"AZURE_OPENAI_API_VERSION_4O: {AZURE_OPENAI_API_VERSION_4O}")
  print(f"AZURE_OPENAI_RESOURCE_O3_MINI: {os.getenv('AZURE_OPENAI_RESOURCE_O3_MINI')}")
  print(f"AZURE_OPENAI_MODEL_O3_MINI: {os.getenv('AZURE_OPENAI_MODEL_O3_MINI')}")
  print(f"AZURE_OPENAI_API_VERSION_O3_MINI: {os.getenv('AZURE_OPENAI_API_VERSION_O3_MINI')}")
  print(f"AZURE_OPENAI_RESOURCE_O1: {os.getenv('AZURE_OPENAI_RESOURCE_O1')}")
  print(f"AZURE_OPENAI_MODEL_O1: {os.getenv('AZURE_OPENAI_MODEL_O1')}")
  print(f"AZURE_OPENAI_API_VERSION_O1: {os.getenv('AZURE_OPENAI_API_VERSION_O1')}")
  print(f"AZURE_OPENAI_RESOURCE_O1_MINI: {os.getenv('AZURE_OPENAI_RESOURCE_O1_MINI')}")
  print(f"AZURE_OPENAI_MODEL_O1_MINI: {os.getenv('AZURE_OPENAI_MODEL_O1_MINI')}")
  print(f"AZURE_OPENAI_API_VERSION_O1_MINI: {os.getenv('AZURE_OPENAI_API_VERSION_O1_MINI')}")

  print(f"AZURE_STORAGE_ACCOUNT_NAME: {AZURE_STORAGE_ACCOUNT_NAME}")
  print(f"AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME: {AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME}")
  print(f"AZURE_STORAGE_OUTPUT_CONTAINER_NAME: {AZURE_STORAGE_OUTPUT_CONTAINER_NAME}")
  print(f"STORAGE_QUEUE_NAME: {STORAGE_QUEUE_NAME}")
  print(f"AZURE_STORAGE_ACCOUNT_ID: {os.getenv('AZURE_STORAGE_ACCOUNT_ID')}")
  print(f"AZURE_STORAGE_QUEUE_NAME: {os.getenv('AZURE_STORAGE_QUEUE_NAME')}")
  print(f"AZURE_STORAGE_BLOB_ENDPOINT: {os.getenv('AZURE_STORAGE_BLOB_ENDPOINT')}")
  print(f"AZURE_STORAGE_QUEUE_ENDPOINT: {os.getenv('AZURE_STORAGE_QUEUE_ENDPOINT')}")
  print(f"AZURE_STORAGE_OUTPUT_CONTAINER_NAME: {AZURE_STORAGE_OUTPUT_CONTAINER_NAME}")
  print(f"AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME: {os.getenv('AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME')}")
  print(f"AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME: {AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME}")

print("version 1.0.3")


# Get credential object
credential = DefaultAzureCredential(logging_enable=False)

async def receive_messages():
  # create a Service Bus client using the connection string
  async with ServiceBusClient(
    fully_qualified_namespace = fully_qualified_namespace,
    credential = credential,
    logging_enable = True) as servicebus_client:

    async with servicebus_client:
      # Get the Queue Receiver object for the input queue
      receiver = servicebus_client.get_queue_receiver(queue_name = queue_name)
      async with receiver:
        try:
          received_msgs = await receiver.receive_messages(max_wait_time = max_wait_time, max_message_count = max_message_count)

          if len(received_msgs) == 0:
            return
          for i, msg in enumerate(received_msgs):
            # Check if message contains an integer value
            try:
              # For the main dictionary
              logger.info(f"[{i}] Received message: {str(msg)}")
              msg = json.loads(str(msg))
              logger.info(f"[{i}] Received message: {str(msg)}")

              topic = msg.get("topic")
              subject = msg.get("subject")
              eventType = msg.get("eventType")
              id = msg.get("id")
              data = msg.get("data")
              dataVersion = msg.get("dataVersion")
              metadataVersion = msg.get("metadataVersion")
              eventTime = msg.get("eventTime")

              # For the nested data dictionary
              api = data.get("api")
              clientRequestId = data.get("clientRequestId")
              requestId = data.get("requestId")
              eTag = data.get("eTag")
              contentType = data.get("contentType")
              contentLength = data.get("contentLength")
              blobType = data.get("blobType")
              accessTier = data.get("accessTier")
              url = data.get("url")
              sequencer = data.get("sequencer")
              storageDiagnostics = data.get("storageDiagnostics")
              batchId = storageDiagnostics["batchId"]

              storage = AzureBlobStorage()
              filename = url.split("/")[-1]
              destination_file_path = os.path.join(os.getcwd(), filename)
              logger.info(f"AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME {AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME}")
              logger.info(f"filename {filename}")
              logger.info(f"destination_file_path {destination_file_path}")
              storage.download_blob(container_name=AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME, 
                                    blob_name=filename, 
                                    destination_file_path=destination_file_path)
              
                      
              with open(destination_file_path, 'r') as f:
                json_file = json.load(f)

              # Load the configuration later
              config = ProcessingPipelineConfiguration.from_json_dict(json_file['configuration'])
              config.pdf_path = storage.download_blob_url(config.pdf_path)
              
              logger.info(f"[{i}] Loaded Config: {str(config)}")

              search_config = AISearchConfig(index_name = AZURE_AI_SEARCH_INDEX_NAME)
              
              job = DocumentIngestionJob(config=config, search_config=search_config)
              document = job.execute_job(container_name=AZURE_STORAGE_OUTPUT_CONTAINER_NAME)
              print(f"[{i}] Document processing job executed successfully.")
              break
            except Exception as e:
              print(f"[{i}] Received message {str(msg)}: {e}")
              continue
            finally:
              # Complete the message so that the message is removed from the queue
              await receiver.complete_message(msg)
              received_msgs.remove(msg)
              print(f"[{i}] Completed message: {str(msg)}")
        except Exception as e:
          print(f"An error occurred while receiving messages from the {queue_name} queue: {e}")
        finally:  
          await receiver.close()
          print(f"Receiver closed for queue: {queue_name}")
          await servicebus_client.close()


# Receive messages from the input queue
asyncio.run(receive_messages())

# Close credential object when it's no longer needed
asyncio.run(credential.close())            
