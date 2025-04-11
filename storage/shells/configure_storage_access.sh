#!/bin/bash

# Script to assign storage roles and configure network access on Azure Storage Account
# Usage: ./configure_storage_access.sh --resource-group <resource-group> --storage-account <storage-account> --principal-id <principal-id> [--network-action Allow|Deny]

# Default values
RESOURCE_GROUP=""
STORAGE_ACCOUNT=""
PRINCIPAL_ID=""
NETWORK_ACTION="Allow"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --resource-group|-g)
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --storage-account|-s)
      STORAGE_ACCOUNT="$2"
      shift 2
      ;;
    --principal-id|-p)
      PRINCIPAL_ID="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --resource-group, -g     Resource group name containing the storage account"
      echo "  --storage-account, -s    Name of the storage account"
      echo "  --principal-id, -p       Principal ID to grant storage roles to (e.g., managed identity)"
      echo "  --network-action, -n     Network action (Allow or Deny) for storage account (default: Allow)"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done

# Check required parameters
if [[ -z "$RESOURCE_GROUP" ]]; then
  echo "Error: Resource group name is required (--resource-group)"
  exit 1
fi

if [[ -z "$STORAGE_ACCOUNT" ]]; then
  echo "Error: Storage account name is required (--storage-account)"
  exit 1
fi

if [[ -z "$PRINCIPAL_ID" ]]; then
  echo "Error: Principal ID is required (--principal-id)"
  exit 1
fi

# Verify network action is valid
if [[ "$NETWORK_ACTION" != "Allow" && "$NETWORK_ACTION" != "Deny" ]]; then
  echo "Error: Network action must be 'Allow' or 'Deny'"
  exit 1
fi

# Ensure user is logged in to Azure
echo "Checking Azure login status..."
ACCOUNT=$(az account show --query name -o tsv 2>/dev/null)
if [[ -z "$ACCOUNT" ]]; then
  echo "You are not logged in to Azure. Please run 'az login' first."
  exit 1
fi
echo "Logged in as: $ACCOUNT"

# Get storage account ID
echo "Getting storage account ID..."
STORAGE_ACCOUNT_ID=$(az storage account show --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" --query id -o tsv)
# Remove any carriage returns or whitespace from the ID
STORAGE_ACCOUNT_ID=$(echo "$STORAGE_ACCOUNT_ID" | tr -d '\r' | xargs)
if [[ -z "$STORAGE_ACCOUNT_ID" ]]; then
  echo "Error: Could not retrieve storage account ID. Please check the storage account name and resource group."
  exit 1
fi
echo "Storage Account ID: $STORAGE_ACCOUNT_ID"

# Assign Storage Blob Data Contributor role
echo "Assigning Storage Blob Data Contributor role..."
az role assignment create \
  --role "ba92f5b4-2d11-453d-a403-e96b0029c9fe" \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type User \
  --scope "$STORAGE_ACCOUNT_ID" \
  --verbose 
  
BLOB_ROLE_SUCCESS=$?
if [ $BLOB_ROLE_SUCCESS -eq 0 ]; then
  echo "Successfully assigned Storage Blob Data Contributor role."
else
  echo "Error: Failed to assign Storage Blob Data Contributor role."
  exit $BLOB_ROLE_SUCCESS
fi

# Assign Storage Queue Data Contributor role
echo "Assigning Storage Queue Data Contributor role..."
az role assignment create \
  --role "974c5e8b-45b9-4653-ba55-5f855dd0fb88" \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type User \
  --scope "$STORAGE_ACCOUNT_ID" \
  --verbose

QUEUE_ROLE_SUCCESS=$?
if [ $QUEUE_ROLE_SUCCESS -eq 0 ]; then
  echo "Successfully assigned Storage Queue Data Contributor role."
else
  echo "Error: Failed to assign Storage Queue Data Contributor role."
  exit $QUEUE_ROLE_SUCCESS
fi

# Update storage account network access
echo "Updating storage account network access to public..."
az storage account update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --public-network-access Enabled \
  --verbose 

NETWORK_UPDATE_SUCCESS=$?
if [ $NETWORK_UPDATE_SUCCESS -eq 0 ]; then
  echo "Successfully updated storage account network access to $NETWORK_ACTION."
else
  echo "Error: Failed to update storage account network access."
  exit $NETWORK_UPDATE_SUCCESS
fi

echo "Configuration completed successfully."