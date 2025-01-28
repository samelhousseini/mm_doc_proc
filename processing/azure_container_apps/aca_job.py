# aca_job.py

import logging
import json
import os
import uuid
from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers.models import *

from env_vars import AML_SUBSCRIPTION_ID, AML_RESOURCE_GROUP

class ACAJob:
    def __init__(self):
        self.subscription_id = AML_SUBSCRIPTION_ID
        self.resource_group = AML_RESOURCE_GROUP
        self.job_name = f"job-{str(uuid.uuid4())[:6]}" #os.getenv("INGESTION_JOB_NAME")
        self.environment_name = os.getenv("CONTAINERAPPS_ENVIRONMENT")
        self.credential = DefaultAzureCredential()
        self.client = ContainerAppsAPIClient(
            credential=self.credential,
            subscription_id=self.subscription_id
        )

        print(f"Subscription ID: {self.subscription_id}")
        print(f"Resource group: {self.resource_group}")
        print(f"Job name: {self.job_name}")
        print(f"Environment name: {self.environment_name}")
        

    def submit_job(self, ingestion_params):
        try:
            logging.info("Submitting Azure Container Apps job.")

            # Create or update the job definition
            job_definition = {
                "location": os.getenv("CONTAINERAPPS_LOCATION"),
                "properties": {
                    "environmentId": f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}/providers/Microsoft.App/managedEnvironments/{self.environment_name}",
                    "configuration": {
                        "triggerType": "Manual",
                        "replicaRetryLimit": 10,
                        "replicaTimeout": 10*24*60*60,
                        "manualTriggerConfig": {
                            "parallelism": 1,
                            "replicaCompletionCount": 1
                        }
                    },
                    "template": {
                        "containers": [
                            {
                                "name": self.job_name,
                                "image": os.getenv("INGESTION_IMAGE"),  # Ensure this environment variable is set to your container image
                                "args": [
                                    "python",
                                    "ingest_doc.py",
                                    "--ingestion_params_dict",
                                    json.dumps(ingestion_params)
                                ],
                                "resources": {
                                    "cpu": os.getenv("CONTAINER_CPU") or 0.5,
                                    "memory": os.getenv("CONTAINER_MEMORY") or "1Gi"
                                }
                            }
                        ]
                    }
                }
            }

            # Create or update the job
            poller = self.client.jobs.begin_create_or_update(
                resource_group_name=self.resource_group,
                job_name=self.job_name,
                job_envelope=job_definition
            )
            job = poller.result()

            # Start the job execution
            job_execution_name = f"{self.job_name}-execution"
            start_poller = self.client.jobs.begin_create_job_execution(
                resource_group_name=self.resource_group,
                job_name=self.job_name,
                job_execution_name=job_execution_name
            )
            result = start_poller.result()
            logging.info(f"Job submitted successfully. Job execution ID: {result.name}")
            return result.name

        except Exception as e:
            logging.error(f"Error submitting ACA job: {e}")
            return None

    def get_job_status(self, job_execution_id):
        try:
            job_execution = self.client.jobs.get_execution(
                resource_group_name=self.resource_group,
                job_name=self.job_name,
                job_execution_name=job_execution_id
            )
            status = job_execution.properties.provisioning_state
            logging.info(f"Job execution {job_execution_id} status: {status}")
            return status
        except Exception as e:
            logging.error(f"Error getting job status: {e}")
            return None
