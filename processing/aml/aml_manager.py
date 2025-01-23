import os
import logging
import tempfile

from typing import Optional

# Azure ML v2 SDK imports
from azure.ai.ml import MLClient, command, Input
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, AzureCliCredential

# AML compute & resource entities
from azure.ai.ml.entities import (
    AmlCompute,
    AzureBlobDatastore,
    Environment as MLEnvironment
)

from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import HttpResponseError
from azure.ai.ml.entities import AzureBlobDatastore
from azure.ai.ml.entities import Environment as MLEnvironment
from azure.ai.ml.entities import AmlCompute

# For user-assigned identity & RBAC role assignment (unchanged from older code)
try:
    from azure.mgmt.authorization import AuthorizationManagementClient
    from azure.mgmt.msi import ManagedServiceIdentityClient
    from azure.mgmt.msi.v2023_01_31.models import Identity
except ImportError:
    logging.warning("azure-mgmt-authorization, azure-mgmt-msi not installed. MSI or RBAC features may fail.")


class AMLManagerV2:
    """
    A sample manager class using Azure ML v2 (azure-ai-ml) with the 'command' factory
    function to define and run jobs. Demonstrates:
      - Connecting to AML workspace
      - Creating/Getting compute
      - Creating/Getting a blob datastore
      - Creating/Getting an environment
      - Submitting a command job
      - Checking job status
      - Using user-assigned identity & RBAC
    """

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        workspace_name: str,
        account_name: str,
        container_name: str,
        account_key: Optional[str] = None
    ):
        """
        :param subscription_id: Azure subscription ID
        :param resource_group: Resource group containing the AML workspace
        :param workspace_name: The name of the AML workspace
        :param account_name: Name of the Azure blob storage account
        :param container_name: Name of the blob container
        :param account_key: Optional storage account key (useful if not purely using MSI)
        """

        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.workspace_name = workspace_name

        # Blob storage details
        self.account_name = account_name
        self.container_name = container_name
        self.account_key = account_key

        # Defaults
        self.blob_datastore_name = "my_blob_datastore"
        self.compute_name = os.getenv("AML_CLUSTER_NAME", "cpu-cluster")
        self.environment_name = "mm_doc_proc_env"
        self.experiment_name = "blob_experiments"
        self.default_location = os.getenv("AML_LOCATION", "eastus")

        # Attempt to authenticate with DefaultAzureCredential
        try:
            credential = DefaultAzureCredential()
        except Exception:
            credential = AzureCliCredential()

        # Connect to AML workspace
        self.ml_client = MLClient(
            credential=credential,
            subscription_id=self.subscription_id,
            resource_group_name=self.resource_group,
            workspace_name=self.workspace_name
        )

        logging.info(
            f"Connected to AML workspace '{self.workspace_name}' "
            f"in subscription '{self.subscription_id}', resource group '{self.resource_group}'."
        )

        # Setup role assignment & MSI clients
        self.credential = credential
        try:
            self.authz_client = AuthorizationManagementClient(credential, self.subscription_id)
            self.msi_client = ManagedServiceIdentityClient(credential, self.subscription_id)
        except Exception as ex:
            logging.warning(f"Could not initialize Azure RBAC/MSI clients: {ex}")
            self.authz_client = None
            self.msi_client = None

        self.user_assigned_identity_principal_id = None

    # --------------------------------------------------------------------------
    # User-Assigned Identity & RBAC
    # --------------------------------------------------------------------------
    def create_or_get_user_assigned_identity(self, identity_name: str) -> str:
        if not self.msi_client:
            raise RuntimeError("MSI client not initialized. Check your credentials/packages.")

        try:
            existing_identity = self.msi_client.user_assigned_identities.get(
                resource_group_name=self.resource_group,
                resource_name=identity_name
            )
            if existing_identity:
                logging.info(f"User-assigned identity '{identity_name}' already exists.")
                self.user_assigned_identity_principal_id = existing_identity.principal_id
                return existing_identity.principal_id
        except HttpResponseError:
            pass

        logging.info(f"Creating user-assigned identity '{identity_name}'...")
        identity_params = Identity(location=self.default_location)
        identity_result = self.msi_client.user_assigned_identities.create_or_update(
            resource_group_name=self.resource_group,
            resource_name=identity_name,
            parameters=identity_params
        )
        logging.info(f"Created identity '{identity_name}' with principal ID: {identity_result.principal_id}")
        self.user_assigned_identity_principal_id = identity_result.principal_id
        return identity_result.principal_id

    def assign_storage_blob_data_contributor_if_not_exists(self, principal_id: str, storage_account_name: str):
        if not self.authz_client:
            raise RuntimeError("AuthorizationManagementClient not initialized. Check your credentials.")

        storage_scope = (
            f"/subscriptions/{self.subscription_id}/"
            f"resourceGroups/{self.resource_group}/"
            f"providers/Microsoft.Storage/storageAccounts/{storage_account_name}"
        )

        role_name = "Storage Blob Data Contributor"
        try:
            role_defs = list(
                self.authz_client.role_definitions.list(
                    scope=f"/subscriptions/{self.subscription_id}",
                    filter=f"roleName eq '{role_name}'"
                )
            )
        except HttpResponseError as e:
            raise ValueError(f"Could not query role definitions: {e}")

        if not role_defs:
            raise ValueError(f"Role definition not found for '{role_name}'")
        role_def_id = role_defs[0].id.lower()

        existing_assignments = self.authz_client.role_assignments.list_for_scope(storage_scope)
        for assignment in existing_assignments:
            if assignment.principal_id == principal_id and assignment.role_definition_id.lower() == role_def_id:
                logging.info(f"Role assignment already exists for principal {principal_id}.")
                return

        import uuid
        assignment_name = str(uuid.uuid4())
        params = {
            "role_definition_id": role_defs[0].id,
            "principal_id": principal_id
        }
        self.authz_client.role_assignments.create(
            scope=storage_scope,
            role_assignment_name=assignment_name,
            parameters=params
        )
        logging.info(f"Assigned 'Storage Blob Data Contributor' to {principal_id} on {storage_scope}.")

    def register_blob_datastore_if_not_exists(
        self,
        datastore_name: str,
        container_name: str,
        account_name: str,
        account_key: str = None
    ):
        """
        Checks if a blob datastore exists by name. If not found, creates one.
        This is equivalent to the "register_blob_datastore_if_not_exists" method in the v1 SDK.

        :param datastore_name: Name for the datastore in AML.
        :param container_name: The Azure Blob container.
        :param account_name: The storage account name.
        :param account_key: Optional storage account key (omit if using MSI/SAS).
        :return: The created or existing Datastore object.
        """
        try:
            existing_ds = self.ml_client.datastores.get(datastore_name)
            print(f"[INFO] Datastore '{datastore_name}' already exists; skipping creation.")
            return existing_ds
        except ResourceNotFoundError:
            pass

        # Create a new Azure Blob datastore entity
        ds_entity = AzureBlobDatastore(
            name=datastore_name,
            account_name=account_name,
            container_name=container_name,
            credentials={"account_key": account_key} if account_key else None,
        )

        # Register or update the datastore in AML
        created_ds = self.ml_client.datastores.create_or_update(ds_entity)
        print(f"[SUCCESS] Registered Blob Datastore '{datastore_name}' with container '{container_name}'.")
        return created_ds
    
    # --------------------------------------------------------------------------
    # Create/Get Compute (v2)
    # --------------------------------------------------------------------------
    def create_or_get_compute(self):
        try:
            compute_resource = self.ml_client.compute.get(self.compute_name)
            logging.info(f"Found existing compute '{self.compute_name}'.")
            return compute_resource
        except ResourceNotFoundError:
            logging.info(f"Compute '{self.compute_name}' not found. Creating...")

        cluster_def = AmlCompute(
            name=self.compute_name,
            type="amlcompute",
            size="STANDARD_D2",
            location=self.default_location,
            min_instances=0,
            max_instances=3,
            idle_time_before_scale_down=2400
        )
        cluster = self.ml_client.compute.begin_create_or_update(cluster_def).result()
        logging.info(f"Created compute '{self.compute_name}'.")
        return cluster

    # --------------------------------------------------------------------------
    # Create/Get Blob Datastore (v2)
    # --------------------------------------------------------------------------
    def create_or_get_blob_datastore(self):
        try:
            ds = self.ml_client.datastores.get(self.blob_datastore_name)
            logging.info(f"Datastore '{self.blob_datastore_name}' found.")
            return ds
        except ResourceNotFoundError:
            logging.info(f"Datastore '{self.blob_datastore_name}' not found. Creating...")

        ds_entity = AzureBlobDatastore(
            name=self.blob_datastore_name,
            account_name=self.account_name,
            container_name=self.container_name,
            credentials={"account_key": self.account_key} if self.account_key else None
        )
        ds = self.ml_client.datastores.create_or_update(ds_entity)
        logging.info(f"Created Blob Datastore '{self.blob_datastore_name}'.")
        return ds

    # --------------------------------------------------------------------------
    # Create/Get Environment (v2)
    # --------------------------------------------------------------------------
    def create_or_get_environment(self, environment_name: str, conda_file_path: str = "conda.yaml"):   
        try:
            env = self.ml_client.environments.get(environment_name, label="latest")
            logging.info(f"Found environment '{environment_name}'.")
            return env
        except ResourceNotFoundError:
            logging.info(f"Environment '{environment_name}' not found. Creating...")

        # A default Docker image if needed
        default_image = "mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest"

        env_def = MLEnvironment(
            name=environment_name,
            image=default_image,
            conda_file=conda_file_path
        )
        new_env = self.ml_client.environments.create_or_update(env_def)
        logging.info(f"Created environment '{environment_name}'.")
        return new_env

    # --------------------------------------------------------------------------
    # SUBMIT A COMMAND JOB (v2) using the command(...) factory
    # --------------------------------------------------------------------------
    def submit_command_job(
        self,
        experiment_name: str,
        job_name: str,
        code_dir: str,
        command_string: str,
        environment_name: str,
        compute_name: str,
        inputs: dict = None,
        description: str = None
    ):
        """
        Submits a command job using the functional command(...) approach in azure.ai.ml.
        :param job_name: Unique name for the job
        :param code_dir: Path to your source code folder
        :param command_string: The command to run, e.g. 'python main.py --arg1 val'
        :param environment_name: The AML environment to use (by name@latest)
        :param compute_name: The AML compute cluster
        :param inputs: Optional dictionary of inputs for the job
        :param display_name: Optional display name for the job
        :param description: Optional description for the job
        :return: The created job object
        """
        from azure.ai.ml import command, Input

        # If inputs is None, define an empty dict
        if inputs is None:
            inputs = {}

        # Attempt to retrieve environment to ensure it exists
        try:
            self.ml_client.environments.get(environment_name, label="latest")
        except ResourceNotFoundError as e:
            raise ValueError(f"Environment '{environment_name}' not found: {e}")

        # Build the Command job
        job_def = command(
            experiment_name=experiment_name,
            code=code_dir,
            command=command_string,
            inputs=inputs,
            environment=f"{environment_name}@latest",
            compute=compute_name,
            display_name=job_name,
            description=description or "Command job via azure.ai.ml.command()"            
        )

        # Submit the job
        created_job = self.ml_client.jobs.create_or_update(job_def, name=job_name)
        logging.info(f"Submitted command job '{job_name}'. Status: {created_job.status}")
        return created_job



    def check_job_status(self, job_name: str):
        job = self.ml_client.jobs.get(job_name)
        logging.info(f"Job '{job_name}' status: {job.status}")
        return job.status
    
    # --------------------------------------------------------------------------
    # Sample: Training a scikit-learn LinearRegression on the Diabetes dataset
    # --------------------------------------------------------------------------
    def submit_sample_job(self):
        """
        Example method that:
        1) Creates/gets compute
        2) Creates/gets environment
        3) Submits a command job that runs a local "main.py" with an input
        """
        self.create_or_get_compute()
        self.create_or_get_blob_datastore()
        env_obj = self.create_or_get_environment(self.environment_name, conda_file_path="conda.yaml")

        script_content = r"""
import os
import logging
logging.basicConfig(level=logging.INFO)

print("Creating a sample CSV file locally...")
csv_path = "sample_output.csv"
with open(csv_path, "w", encoding="utf-8") as f:
    f.write("id,val\n1,Hello\n2,World\n")

print("Done writing sample_output.csv")
"""

        # Write the script to a temp directory
        temp_dir = tempfile.mkdtemp()
        script_name = "sample_script.py"
        script_file = os.path.join(temp_dir, script_name)
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script_content)

        # The command is "python main.py --diabetes-csv ${{inputs.diabetes}}"
        command_str = f"python {script_name}"

        # Submit the job
        experiment_name = "MyAmlExperiments"
        job_name = "sample-job"

        created_job = self.submit_command_job(
            experiment_name=experiment_name,
            job_name=job_name,
            code_dir=temp_dir,
            command_string=command_str,
            environment_name=self.environment_name,
            compute_name=self.compute_name,
            inputs=None,
        )

        # Optionally, wait or check status
        status = self.check_job_status(created_job.name)
        logging.info(f"Job '{job_name}' final status: {status}")
        return created_job





