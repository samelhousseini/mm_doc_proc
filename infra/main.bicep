targetScope = 'subscription'

// Basic parameters
@description('Name for the resource group to deploy all resources')
param resourceGroupName string

@description('Location for the resource group and resources')
param location string

@description('Base name prefix for resources - will be used to generate unique names')
param baseName string = 'docproc'

@description('Create a new resource group if it does not exist?')
param createResourceGroup bool = true

@description('Whether to create a new Azure OpenAI resource or use an existing one')
param createOpenAi bool = true

@description('Name for new Azure OpenAI resource (if createOpenAi = true)')
param openAiResourceName string = ''

@secure()
@description('If NOT creating a new Azure OpenAI resource, supply the existing OpenAI API key')
param existingOpenAiApiKey string 

@description('If NOT creating a new Azure OpenAI resource, supply the OpenAI resource RG')
param existingOpenAiResourceGroup string 

@description('If NOT creating a new Azure OpenAI resource, supply the resource')
param existingOpenAiResource string 

@description('Location for the OpenAI resource')
param existingOpenAILocation string

// Model deployment parameters with environment fallbacks when using existing resources
@description('GPT-4o deployment name')
param gpt4oDeploymentName string = 'gpt-4o'

@description('o1 deployment name')
param o1DeploymentName string = 'o1'

@description('o1-mini deployment name')
param o1MiniDeploymentName string = 'o1-mini'

@description('o3-mini deployment name')
param o3MiniDeploymentName string = 'o3-mini'

@description('Text embedding 3 Large deployment name')
param textEmbedding3LargeDeploymentName string = 'text-embedding-3-large'

// Environment variable values (to use when createOpenAi=false)
param AZURE_OPENAI_MODEL_4O string = 'gpt-4o'
param AZURE_OPENAI_MODEL_O1 string = 'o1'
param AZURE_OPENAI_MODEL_O1_MINI string = 'o1-mini'
param AZURE_OPENAI_MODEL_O3_MINI string = 'o3-mini'
param AZURE_OPENAI_MODEL_EMBEDDING_LARGE string = 'text-embedding-3-large'

// Conditional selection of values based on createOpenAi flag
var finalGpt4oDeploymentName = createOpenAi ? gpt4oDeploymentName : AZURE_OPENAI_MODEL_4O
var finalO1DeploymentName = createOpenAi ? o1DeploymentName : AZURE_OPENAI_MODEL_O1
var finalO1MiniDeploymentName = createOpenAi ? o1MiniDeploymentName : AZURE_OPENAI_MODEL_O1_MINI
var finalO3MiniDeploymentName = createOpenAi ? o3MiniDeploymentName : AZURE_OPENAI_MODEL_O3_MINI
var finalTextEmbedding3LargeDeploymentName = createOpenAi ? textEmbedding3LargeDeploymentName : AZURE_OPENAI_MODEL_EMBEDDING_LARGE

// ------------------ Log Analytics and Application Insights ------------------ //
@description('Whether to create a new Log Analytics workspace for monitoring.')
param createLogAnalytics bool = true

@minLength(4)
@maxLength(63)
@description('Name of the Log Analytics workspace (if creating). If blank, will generate.')
param logAnalyticsName string = 'default-logs'

@description('Name of the Application Insights resource to create. If blank, will generate.')
param appInsightsName string = 'default-appins'


// ------------------ Storage & Event Grid ------------------ //
@minLength(3)
@maxLength(24)
@description('Name of the storage account (if blank, we will generate). Must be globally unique.')
param storageAccountName string 

@description('Whether to create a new storage account or use an existing one')
param createStorage bool = true


@description('Blob container name for JSON uploads.')
param uploadsJsonContainerName string = 'json_data'

@description('Blob container name for JSON uploads.')
param uploadsDocumentContainerName string = 'document_data'

@description('Blob container name for processed documents.')
param processedContainerName string = 'processed'

@description('Queue name for event-driven processing.')
param storageQueueName string = 'doc-process-queue'


// ------------------ Cognitive Search Parameters ------------------ //
@description('Whether to create a new Cognitive Search service')
param createSearch bool = true

@minLength(2)
@maxLength(60)
@description('Name for the Cognitive Search service to create (if createSearch = true). If blank, will generate.')
param searchServiceName string = 'default-search'

@description('If not creating new, supply existing search service admin key.')
@secure()
param existingSearchAdminKey string = ''

@description('If not creating new, supply existing search service endpoint')
param existingSearchResource string = ''

@description('If not creating new, supply existing search service resource group')
param existingSearchResourceGroup string = ''

@description('SKU for Cognitive Search (e.g., Basic, S1, etc.). Only relevant if creating new.')
@allowed([
  'basic'
  'standard'
  'standard2'
  'standard3'
])
param searchSku string = 'basic'


// ------------------ Container Apps Job Settings ------------------ //
@description('Name of the Container Apps Environment')
param containerAppsEnvironmentName string = ''

@description('Name of the Container Apps Job')
param containerAppsJobName string = ''

@description('Maximum number of parallel job executions.')
@minValue(1)
@maxValue(20)
param maxParallelExecutions int = 10

@description('Minimum number of executions (0 for scale to zero).')
@allowed([0, 1])
param minExecutions int = 0

@description('CPU cores allocated to the job container.')
param containerCpuCores string = '1.0'

@description('Memory allocated to the job container in gigabytes.')
param containerMemoryGb string = '2.0'


// ------------------ GitHub Repository Settings ------------------ //
@description('GitHub repository URL containing the document processor code.')
param gitHubRepoUrl string = 'https://github.com/samelhousseini/mm_doc_proc.git'

@description('GitHub repository branch to use.')
param gitHubRepoBranch string = 'main'

@description('Dockerfile path relative to the repository root.')
param dockerfilePath string = 'Dockerfile'


// ------------------ Service Bus Parameters ------------------ //
@description('Whether to create a Service Bus namespace')
param createServiceBus bool = true

@description('Name for the Service Bus namespace (if blank, will generate)')
param serviceBusNamespaceName string = ''

@description('SKU for Service Bus namespace')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param serviceBusSku string = 'Standard'

@description('Capacity for Service Bus namespace (only for Premium SKU)')
@minValue(1)
@maxValue(8)
param serviceBusCapacity int = 1

@description('Names of queues to create in the Service Bus namespace')
param serviceBusQueueNames array = ['document-processing-queue']

@description('Lock duration for messages in queues')
param queueLockDuration string = 'PT5M'

@description('Maximum delivery count for messages before dead-lettering')
@minValue(1)
@maxValue(100)
param queueMaxDeliveryCount int = 10

@description('Enable duplicate detection on queues')
param queueRequiresDuplicateDetection bool = false

@description('Enable sessions on queues')
param queueRequiresSession bool = false

@description('Enable dead-lettering on message expiration')
param queueDeadLetteringOnExpiration bool = true

@description('Time window for duplicate detection history')
param queueDuplicateDetectionWindow string = 'PT10M'


// ------------------ Cosmos DB Parameters ------------------ //
@description('Name for the CosmosDB database')
param cosmosDbDatabaseName string = 'proc-docs'

@description('Name for the CosmosDB container')
param cosmosDbContainerName string = 'documents'

@description('Name for the partition key field in CosmosDB')
param cosmosDbPartitionKeyName string = 'categoryId'

@description('Value of the partition key used for categorization in CosmosDB')
param cosmosDbPartitionKeyValue string = 'documents'



// ------------------ Resource Deployments ------------------ //

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: {
    application: 'document-processor'
    environment: 'production'
  }
}

// Common tags for all resources
var tags = {
  application: 'document-processor'
  environment: 'production'
  deployment: 'bicep'
}

// Generate unique values if needed
var randomSuffix = uniqueString(subscription().id, resourceGroupName, baseName)
var defaultOpenAiName = '${baseName}-openai-${take(randomSuffix, 5)}'
var openAiNameGenerated = !empty(openAiResourceName) ? openAiResourceName : defaultOpenAiName
var storageNameGenerated = empty(storageAccountName) ? toLower(replace('${baseName}st${take(randomSuffix, 8)}', '-', '')) : storageAccountName
var logAnalyticsNameGenerated = empty(logAnalyticsName) ? '${baseName}-logs-${take(randomSuffix, 5)}' : logAnalyticsName
var appInsightsNameGenerated = empty(appInsightsName) ? '${baseName}-appins-${take(randomSuffix, 5)}' : appInsightsName
var searchNameGenerated = createSearch ? (empty(searchServiceName) ? '${baseName}-search-${take(randomSuffix, 5)}' : searchServiceName) : ''
var containerAppsJobNameGenerated = empty(containerAppsJobName) ? '${baseName}-job-${take(randomSuffix, 5)}' : containerAppsJobName
var containerAppsEnvironmentNameGenerated = empty(containerAppsEnvironmentName) ? '${baseName}-env-${take(randomSuffix, 5)}' : containerAppsEnvironmentName
var serviceBusNamespaceNameGenerated = createServiceBus ? (empty(serviceBusNamespaceName) ? '${baseName}-sb-${take(randomSuffix, 5)}' : serviceBusNamespaceName) : ''
var uniqueId = uniqueString(rg.id)



// ------------------ Module Deployments ------------------ //
// User Assigned Managed Identity

module uami 'modules/uami.bicep' = {
  name: 'uami'
  scope: rg
  params: {
    uniqueId: uniqueId
    prefix: baseName
    location: location
  }
}


module appin 'modules/appin.bicep' = {
  name: 'appin'
  scope: rg
  params: {
    uniqueId: uniqueId
    prefix: baseName
    location: location
    userAssignedIdentityPrincipalId: uami.outputs.principalId
  }
}


// Monitoring Resources (Log Analytics & Application Insights)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    createLogAnalytics: createLogAnalytics
    logAnalyticsName: logAnalyticsNameGenerated
    appInsightsName: appInsightsNameGenerated
    tags: tags
    userAssignedIdentityPrincipalId: uami.outputs.principalId
  }
}

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    createStorage: createStorage
    storageAccountName: storageNameGenerated
    uploadsJsonContainerName: uploadsJsonContainerName
    uploadsDocumentContainerName: uploadsDocumentContainerName
    processedContainerName: processedContainerName
    storageQueueName: storageQueueName
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
    userAssignedIdentityPrincipalId: uami.outputs.principalId
  }
}



module namespace 'modules/service-bus.bicep' = {
  name: 'service-bus-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    name: serviceBusNamespaceNameGenerated
    location: location
    tags: tags
    zoneRedundant: serviceBusSku == 'Premium'
    skuName: serviceBusSku
    capacity: serviceBusCapacity
    queueNames: serviceBusQueueNames
    lockDuration: queueLockDuration
    maxDeliveryCount: queueMaxDeliveryCount
    requiresDuplicateDetection: queueRequiresDuplicateDetection
    requiresSession: queueRequiresSession
    deadLetteringOnMessageExpiration: queueDeadLetteringOnExpiration
    duplicateDetectionHistoryTimeWindow: queueDuplicateDetectionWindow
    workspaceId: monitoring.outputs.logAnalyticsId
    userAssignedIdentityPrincipalId: uami.outputs.principalId
  }
}

// Event Grid subscription connecting Storage Events to Service Bus queue
module eventGridServiceBusIntegration 'modules/eventgrid-servicebus.bicep' = {
  name: 'eventgrid-servicebus-integration'
  scope: resourceGroup(resourceGroupName)
  params: {
    namespaceId: namespace.outputs.id
    eventGridSystemTopicId: storage.outputs.blobEventGridSystemTopicId
    serviceBusQueueId: namespace.outputs.queues[0].id
    userAssignedIdentityId: uami.outputs.identityId
    eventGridSubscriptionName: 'blob-to-servicebus'
    blobEventTypes: [
      'Microsoft.Storage.BlobCreated'
    ]
    subjectFilters: {
      subjectBeginsWith: '/blobServices/default/containers/${storage.outputs.uploadsJsonContainerName}'
      subjectEndsWith: ''
    }
  }
  dependsOn: [
    storage
    namespace
  ]
}

module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    uniqueId: uniqueId
    prefix: baseName
    userAssignedIdentityPrincipalId: uami.outputs.principalId
    databaseName: cosmosDbDatabaseName
    containerName: cosmosDbContainerName
    partitionKeyName: cosmosDbPartitionKeyName
    partitionKeyValue: cosmosDbPartitionKeyValue
    location: location
  }
}


// OpenAI Module
module openai 'modules/openai.bicep' = {
  name: existingOpenAiResource
  scope: resourceGroup(existingOpenAiResourceGroup)
  params: {
    location: existingOpenAILocation
    createOpenAi: createOpenAi
    openAiResourceName: openAiNameGenerated
    existingOpenAiApiKey: existingOpenAiApiKey
    existingOpenAiResource: existingOpenAiResource
    gpt4oDeploymentName: finalGpt4oDeploymentName
    o1DeploymentName: finalO1DeploymentName
    o1MiniDeploymentName: finalO1MiniDeploymentName
    o3MiniDeploymentName: finalO3MiniDeploymentName
    textEmbedding3LargeDeploymentName: finalTextEmbedding3LargeDeploymentName
    userAssignedIdentityPrincipalId: uami.outputs.principalId
    tags: tags
  }
}

module acrModule 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    uniqueId: uniqueId
    prefix: baseName
    userAssignedIdentityPrincipalId: uami.outputs.principalId
    location: location
  }
}

// Azure AI Search (Cognitive Search)
module search 'modules/search.bicep' = {
  name: 'search-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    createSearch: createSearch 
    searchServiceName: searchNameGenerated
    existingSearchAdminKey: existingSearchAdminKey
    existingSearchResource: existingSearchResource
    searchSku: searchSku
    tags: tags
    userAssignedIdentityPrincipalId: uami.outputs.principalId
  }
}


// Build and push the container image to ACR
module acrBuild 'modules/acr-build.bicep' = {
  name: 'acr-build-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    acrName: acrModule.outputs.acrName
    location: location
    gitHubRepoUrl: gitHubRepoUrl
    gitHubBranch: gitHubRepoBranch
    dockerfilePath: dockerfilePath
    imageName: 'mm-doc-processor:latest'
    timestamp: 'timestamp-${deployment().name}'
  }
  dependsOn: [
    acrModule
    storage
    monitoring
    appin
    openai
    search
    uami
    cosmos
  ]
}


// Container Apps Environment and Job
module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps-deployment'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    environmentName: containerAppsEnvironmentNameGenerated
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
    jobName: containerAppsJobNameGenerated
    acrLoginServer: acrModule.outputs.acrEndpoint
    imageName: 'mm-doc-processor:latest'
    maxParallelExecutions: maxParallelExecutions
    minExecutions: minExecutions
    containerCpuCores: containerCpuCores
    containerMemoryGb: containerMemoryGb
    managedIdentityId: uami.outputs.identityId
    tags: tags
    secrets: [
      {
        name: 'service-bus-connection-string'
        value: namespace.outputs.connectionString
      }
    ]
    eventRules: [
      {
        name: 'azure-servicebus-queue-rule'
        type: 'azure-servicebus'
        metadata: {
          messageCount: '5'
          namespace: serviceBusNamespaceNameGenerated
          queueName: serviceBusQueueNames[0]
        }
        identity: uami.outputs.identityId
        auth: [
          {
            secretRef: 'service-bus-connection-string'
            triggerParameter: 'connection'
          }
        ]
      }
    ]
    environmentVariables: [
      {
        name: 'AZURE_CLIENT_ID'
        value: uami.outputs.clientId
      }
      {
        name: 'AZURE_OPENAI_RESOURCE_4O'
        value: openai.outputs.openAiName
      }
      {
        name: 'AZURE_OPENAI_MODEL_4O'
        value: gpt4oDeploymentName
      }
      {
        name: 'AZURE_OPENAI_API_VERSION_4O'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_OPENAI_RESOURCE_O3_MINI'
        value: openai.outputs.openAiName
      }
      {
        name: 'AZURE_OPENAI_MODEL_O3_MINI'
        value: o3MiniDeploymentName
      }
      {
        name: 'AZURE_OPENAI_API_VERSION_O3_MINI'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_OPENAI_RESOURCE_O1'
        value: openai.outputs.openAiName
      }
      {
        name: 'AZURE_OPENAI_MODEL_O1'
        value: o1DeploymentName
      }
      {
        name: 'AZURE_OPENAI_API_VERSION_O1'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_OPENAI_RESOURCE_O1_MINI'
        value: openai.outputs.openAiName
      }
      {
        name: 'AZURE_OPENAI_MODEL_O1_MINI'
        value: o1MiniDeploymentName
      }
      {
        name: 'AZURE_OPENAI_API_VERSION_O1_MINI'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE'
        value: openai.outputs.openAiName
      }
      {
        name: 'AZURE_OPENAI_MODEL_EMBEDDING_LARGE'
        value: textEmbedding3LargeDeploymentName
      }
      {
        name: 'AZURE_OPENAI_API_VERSION_EMBEDDING_LARGE'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_AI_SEARCH_SERVICE_NAME'
        value: search.outputs.searchServiceEndpoint
      }
      {
        name: 'AZURE_AI_SEARCH_API_KEY'
        value: search.outputs.searchServiceKey
      }
      {
        name: 'AZURE_STORAGE_ACCOUNT_NAME'
        value: storage.outputs.storageAccountName
      }
      {
        name: 'AZURE_STORAGE_UPLOAD_JSON_CONTAINER_NAME'
        value: uploadsJsonContainerName
      }
      {
        name: 'AZURE_STORAGE_UPLOAD_DOCUMENT_CONTAINER_NAME'
        value: uploadsDocumentContainerName
      }
      {
        name: 'AZURE_STORAGE_ACCOUNT_ID'
        value: storage.outputs.storageAccountId
      }
      {
        name: 'AZURE_STORAGE_QUEUE_NAME'
        value: storage.outputs.queueName
      }
      {
        name: 'AZURE_STORAGE_BLOB_ENDPOINT'
        value: storage.outputs.storageBlobEndpoint
      }
      {
        name: 'AZURE_STORAGE_QUEUE_ENDPOINT'
        value: storage.outputs.storageQueueEndpoint
      }
      {
        name: 'AZURE_STORAGE_OUTPUT_CONTAINER_NAME'
        value: processedContainerName
      }
      {
        name: 'APP_INSIGHTS_CONN_STRING'
        value: monitoring.outputs.appInsightsConnectionString
      }
      {
        name: 'COSMOS_URI'
        value: cosmos.outputs.cosmosDbEndpoint
      }
      {
        name: 'COSMOS_DB_NAME'
        value: cosmos.outputs.cosmosDbDatabase
      }
      {
        name: 'COSMOS_CONTAINER_NAME'
        value: cosmos.outputs.cosmosDbContainer
      }
      {
        name: 'COSMOS_CATEGORYID'
        value: cosmos.outputs.partitionKeyName
      }
      {
        name: 'COSMOS_CATEGORYID_VALUE'
        value: cosmos.outputs.partitionKeyValue
      }
      {
        name: 'COSMOS_LOG_CONTAINER'
        value: 'logs'
      }
      {
        name: 'SERVICE_BUS_NAME'
        value: namespace.outputs.name
      }
      {
        name: 'SERVICE_BUS_QUEUE_NAME'
        value: serviceBusQueueNames[0]
      }
      {
        name: 'SERVICE_BUS_CONNECTION_STRING'
        value: namespace.outputs.connectionString
      }
      {
        name: 'AZURE_OPENAI_API_KEY'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
      {
        name: 'AZURE_OPENAI_ENDPOINT'
        value: openai.outputs.openAiEndpoint
      }
      {
        name: 'AZURE_OPENAI_API_VERSION'
        value: '2024-12-01-preview'
      }
      {
        name: 'AZURE_OPENAI_API_KEY_O3_MINI'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
      {
        name: 'AZURE_OPENAI_API_KEY_O1'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
      {
        name: 'AZURE_OPENAI_API_KEY_O1_MINI'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
      {
        name: 'AZURE_OPENAI_API_KEY_EMBEDDING_LARGE'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
      {
        name: 'AZURE_OPENAI_API_KEY_4O'
        value: openai.outputs.openAiKeyAvailable ? existingOpenAiApiKey : ''
      }
    ]
  }
  dependsOn: [
    rg
    monitoring
    acrModule
    storage
    appin
    openai
    uami
    cosmos
    acrBuild
  ]
}


// Outputs
// User Assigned Managed Identity outputs
output identityName string = uami.outputs.identityId
output identityClientId string = uami.outputs.clientId
output identityPrincipalId string = uami.outputs.principalId

// OpenAI outputs
output openAiName string = openai.outputs.openAiName
output openAiEndpoint string = openai.outputs.openAiEndpoint
output openAiKeyAvailable bool = openai.outputs.openAiKeyAvailable

// Storage Account outputs
output storageAccountName string = storage.outputs.storageAccountName
output storageAccountId string = storage.outputs.storageAccountId
output storageBlobEndpoint string = storage.outputs.storageBlobEndpoint
output storageQueueEndpoint string = storage.outputs.storageQueueEndpoint
output uploadsJsonContainerName string = storage.outputs.uploadsJsonContainerName
output processedContainerName string = storage.outputs.processedContainerName
output storageQueueName string = storage.outputs.queueName
output blobEventGridSystemTopicName string = storage.outputs.blobEventGridSystemTopicName

// Service Bus outputs
output serviceBusNamespace string = namespace.outputs.name
output serviceBusQueues array = namespace.outputs.queues

// Application Insights outputs
output logAnalyticsWorkspaceId string = monitoring.outputs.logAnalyticsId
output appInsightsName string = monitoring.outputs.appInsightsName
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString

// Cognitive Search outputs
output searchServiceName string = search.outputs.searchServiceName
output searchServiceEndpoint string = search.outputs.searchServiceEndpoint

// Cosmos DB outputs
output cosmosDbEndpoint string = cosmos.outputs.cosmosDbEndpoint
output cosmosDbDatabase string = cosmos.outputs.cosmosDbDatabase
output cosmosDbContainer string = cosmos.outputs.cosmosDbContainer

// Container Registry outputs
output acrName string = acrModule.outputs.acrName
output acrEndpoint string = acrModule.outputs.acrEndpoint

// Container Apps outputs  
output containerAppsEnvironmentName string = containerApps.outputs.containerAppsEnvironmentName
output containerAppsJobName string = containerApps.outputs.containerAppsJobName

// Event Grid Service Bus Integration outputs
output eventGridSubscriptionId string = eventGridServiceBusIntegration.outputs.eventGridSubscriptionId
output eventGridSubscriptionName string = eventGridServiceBusIntegration.outputs.eventGridSubscriptionName

// Deployment Debug Information
output deploymentDebugInfo object = {
  generatedNames: {
    openAi: openAiNameGenerated
    storage: storageNameGenerated
    logAnalytics: logAnalyticsNameGenerated
    appInsights: appInsightsNameGenerated
    search: searchNameGenerated
    containerAppsEnvironment: containerAppsEnvironmentNameGenerated
    containerAppsJob: containerAppsJobNameGenerated
    serviceBusNamespace: serviceBusNamespaceNameGenerated
  }
  status: {
    openAi: createOpenAi ? 'Creating new resource' : 'Using existing resource'
    storage: createStorage ? 'Creating new resource' : 'Using existing resource'
    logAnalytics: createLogAnalytics ? 'Creating new resource' : 'Using existing resource'
    search: createSearch ? 'Creating new resource' : 'Using existing resource'
    serviceBus: createServiceBus ? 'Creating new resource' : 'Using existing resource'
  }
  openAiDeployment: openai.outputs.debugLog
  storageDeployment: storage.outputs.debugLogs
  searchDeployment: search.outputs.debugLogs
  containerAppsDeployment: containerApps.outputs.debugLogs
  deploymentNames: {
    gpt4o: finalGpt4oDeploymentName
    o1: finalO1DeploymentName
    o1Mini: finalO1MiniDeploymentName
    o3Mini: finalO3MiniDeploymentName
    textEmbedding3Large: finalTextEmbedding3LargeDeploymentName
  }
}

// Added parameter value outputs
output resolvedParameters object = {
  resourceGroupName: resourceGroupName
  location: location
  baseName: baseName
  createResourceGroup: createResourceGroup
  createOpenAi: createOpenAi
  openAiResourceName: openAiResourceName
  environmentVariableValues: {
    AZURE_OPENAI_MODEL_4O: AZURE_OPENAI_MODEL_4O
    AZURE_OPENAI_MODEL_O1: AZURE_OPENAI_MODEL_O1
    AZURE_OPENAI_MODEL_O1_MINI: AZURE_OPENAI_MODEL_O1_MINI
    AZURE_OPENAI_MODEL_O3_MINI: AZURE_OPENAI_MODEL_O3_MINI
    AZURE_OPENAI_MODEL_EMBEDDING_LARGE: AZURE_OPENAI_MODEL_EMBEDDING_LARGE
  }
  actualValuesUsed: {
    gpt4oDeploymentName: finalGpt4oDeploymentName
    o1DeploymentName: finalO1DeploymentName
    o1MiniDeploymentName: finalO1MiniDeploymentName
    o3MiniDeploymentName: finalO3MiniDeploymentName
    textEmbedding3LargeDeploymentName: finalTextEmbedding3LargeDeploymentName
  }
}
