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
AZURE_STORAGE_UPLOAD_CONTAINER_NAME = os.getenv("AZURE_STORAGE_UPLOAD_CONTAINER_NAME", "data")
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
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME", "KYC")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_CONTAINER_NAME", "Customers")
COSMOS_LOG_CONTAINER = os.getenv("COSMOS_LOG_CONTAINER", "logs")
SERVICE_BUS_NAME = os.getenv("SERVICE_BUS_NAME", "servicebus")
SERVICE_BUS_QUEUE_NAME = os.getenv("SERVICE_BUS_QUEUE_NAME", 'document-processing-queue')


fully_qualified_namespace=f"{SERVICE_BUS_NAME}.servicebus.windows.net"
queue_name=SERVICE_BUS_QUEUE_NAME
max_wait_time=5
max_message_count=20
MIN_NUMBER=1
MAX_NUMBER=20
MESSAGE_COUNT=100
# SEND_TYPE=list



# Print environment variables
print(f"FULLY_QUALIFIED_NAMESPACE: {fully_qualified_namespace}")
print(f"QUEUE_NAME: {queue_name}")
print(f"MAX_MESSAGE_COUNT: {max_message_count}")
print(f"MAX_WAIT_TIME: {max_wait_time}")
print(f"MIN_NUMBER: {MIN_NUMBER}")
print(f"MAX_NUMBER: {MAX_NUMBER}")
print(f"AZURE_STORAGE_ACCOUNT_NAME: {AZURE_STORAGE_ACCOUNT_NAME}")
print(f"AZURE_STORAGE_UPLOAD_CONTAINER_NAME: {AZURE_STORAGE_UPLOAD_CONTAINER_NAME}")
print(f"AZURE_STORAGE_OUTPUT_CONTAINER_NAME: {AZURE_STORAGE_OUTPUT_CONTAINER_NAME}")
print(f"STORAGE_QUEUE_NAME: {STORAGE_QUEUE_NAME}")
print(f"AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE: {AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE}")
print(f"AZURE_OPENAI_KEY_EMBEDDING_LARGE: {AZURE_OPENAI_KEY_EMBEDDING_LARGE}")
print(f"AZURE_OPENAI_MODEL_EMBEDDING_LARGE: {AZURE_OPENAI_MODEL_EMBEDDING_LARGE}")
print(f"AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE: {AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE}")



# App Insights for monitoring
APP_INSIGHTS_CONN_STRING = os.getenv("APP_INSIGHTS_CONN_STRING")

class DocumentProcessor:
    """Document processor handles document extraction, analysis, and storage"""
    
    def __init__(self):
        """Initialize the document processor with all necessary clients"""
        # Azure credentials
        try:
            self.credential = DefaultAzureCredential()
            logger.info("Using DefaultAzureCredential")

            query = "Hello, how are you?"
            model_info = MulitmodalProcessingModelInfo('gpt-4o')
            response = call_llm(query, model_info=model_info)
            print(response)
            logger.info("LLM call successful:", response)

        except Exception:
            logger.info("Error initializing DefaultAzureCredential")


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
              storage.download_blob(container_name=AZURE_STORAGE_UPLOAD_CONTAINER_NAME, 
                                    blob_name=filename, 
                                    destination_file_path=destination_file_path)
              
              print(f"[{i}] Downloaded blob: {filename} to {destination_file_path}")

              print(f"[{i}] Received message: {str(msg)}")
              config = ProcessingPipelineConfiguration(
                  pdf_path=destination_file_path
              )
              config.multimodal_model = MulitmodalProcessingModelInfo(           
                  model_name="gpt-4o",
              )

              config.text_model = TextProcessingModelnfo(
                  model_name="gpt-4o",           
              )
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
