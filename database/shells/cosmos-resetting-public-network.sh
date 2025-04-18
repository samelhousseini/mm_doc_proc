#!/bin/bash

# SAMPLE USAGE:
# bash cosmos-resetting-public-network.sh --resource-group "<RG>" --account-name "<COSMOS_RESOURCE>"

# Set default values
RESOURCE_GROUP=""
ACCOUNT_NAME=""
SUBSCRIPTION_ID=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --resource-group|-g)
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --account-name|-a)
      ACCOUNT_NAME="$2"
      shift 2
      ;;
    --subscription-id|-i)
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --resource-group, -g     Resource group name"
      echo "  --account-name, -a       Cosmos DB account name"
      echo "  --subscription-id, -i    Subscription ID (optional)"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done

# Set Azure subscription if provided
if [[ -n "$SUBSCRIPTION_ID" ]]; then
  echo "Setting Azure subscription to: $SUBSCRIPTION_ID"
  az account set --subscription "$SUBSCRIPTION_ID"
fi

# Update public network access
echo "Resetting public network access to ENABLED..."
az cosmosdb update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACCOUNT_NAME" \
    --public-network-access ENABLED \
    --subscription "$SUBSCRIPTION_ID" \
    --verbose