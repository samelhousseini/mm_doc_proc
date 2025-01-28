#!/bin/bash

# Check if the subscription ID and resource group name are provided as command-line arguments
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <subscription-id> <resource-group-name>"
  exit 1
fi

# Set the subscription ID and resource group name from the CLI arguments
SUBSCRIPTION_ID="$1"
RESOURCE_GROUP_NAME="$2"

# Set the Azure subscription
az account set --subscription "$SUBSCRIPTION_ID"

# Get ACR registries in the specified resource group, removing any carriage return characters
registries=$(az acr list --resource-group "$RESOURCE_GROUP_NAME" --query "[].name" -o tsv | tr -d '\r')

if [ -z "$registries" ]; then
  echo "[]"
  exit 0
fi

# Initialize an empty array to hold the ACR details
acr_list=()

# Iterate over each ACR and gather relevant information
while IFS= read -r ACR_NAME; do
    # Remove any trailing carriage return characters
    ACR_NAME=$(echo "$ACR_NAME" | tr -d '\r')

    # Enable admin user
    az acr update -n "$ACR_NAME" --admin-enabled true >/dev/null

    # Get ACR login server
    ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query "loginServer" -o tsv | tr -d '[:space:]')

    # Get ACR username
    ACR_USER=$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query "username" -o tsv | tr -d '[:space:]')

    # Get ACR password
    ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query "passwords[0].value" -o tsv | tr -d '[:space:]')

    # Create a JSON object for the current ACR
    acr_info=$(jq -n \
        --arg name "$ACR_NAME" \
        --arg server "$ACR_LOGIN_SERVER" \
        --arg username "$ACR_USER" \
        --arg password "$ACR_PASSWORD" \
        '{name: $name, server: $server, username: $username, password: $password}')

    # Add the JSON object to the array
    acr_list+=("$acr_info")
done <<< "$registries"

# Output the array of ACR details as a JSON array
printf '%s\n' "${acr_list[@]}" | jq -s '.'
