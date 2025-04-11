#!/bin/bash

# SAMPLE USAGE:
# bash storage-resetting-public-network.sh --resource-group "<RG>" --storage-account "<COSMOS_RESOURCE>"

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
    --storage-account|-s)
      STORAGE_ACCOUNT="$2"
      shift 2
      ;;
    --subscription-id|-s)
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --resource-group, -g     Resource group name"
      echo "  --storage-account, -s    Storage account name"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done



# Update storage account network access
echo "Updating storage account network access to public..."
az storage account update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --public-network-access Enabled \
  --verbose 