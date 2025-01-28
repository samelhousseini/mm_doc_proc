from pydantic import BaseModel
from typing import Optional, List, Literal
from utils.openai_data_models import *



class ACAConfiguration(BaseModel):
    subscription_id: str = os.getenv('AZURE_SUBSCRIPTION_ID')
    resource_group: str = os.getenv('AZURE_RESOURCE_GROUP')
    aca_environment: str = os.getenv('AZURE_ACA_ENVIRONMENT')
    acr_name: str = os.getenv('AZURE_ACR_NAME')
    acr_username: str = os.getenv('AZURE_ACR_USERNAME')
    acr_password: str = os.getenv('AZURE_ACR_PASSWORD')
    


class ACAJobConfiguration(BaseModel):
    aca_config: ACAConfiguration = ACAConfiguration()
    job_name: str
    timeout: int = 10*24*60*60
    retry_limit: int = 10
    cpu: float = 0.5
    memory: str = "1Gi"
    parallelism: int = 1
    replica_completion_count: int = 1
    trigger_type: Literal["Manual", "Event"] = "Manual"
    image: str
    args: List[str]
    environment_id: str = f"/subscriptions/{aca_config.subscription_id}/resourceGroups/{aca_config.resource_group}/providers/Microsoft.App/managedEnvironments/{aca_config.aca_environment}"
    location: str = os.getenv("AZURE_LOCATION")
    replica_retry_limit: int = 10
    replica_timeout: int = 10*24*60*60
    manual_trigger_config: dict = {"parallelism": parallelism, "replicaCompletionCount": replica_completion_count}
    containers: List[dict] = [{"name": job_name, "image": image, "args": args, "resources": {"cpu": cpu, "memory": memory}}]
    configuration: dict = {"triggerType": trigger_type, "replicaRetryLimit": retry_limit, "replicaTimeout": timeout, "manualTriggerConfig": manual_trigger_config}
    properties: dict = {"environmentId": environment_id, "configuration": configuration, "template": {"containers": containers}}
    job_definition: dict = {"location": location, "properties": properties}
    job_definition: dict = {"location": location, "properties": properties}
    job_definition: dict = {"location": location, "properties": properties}
    