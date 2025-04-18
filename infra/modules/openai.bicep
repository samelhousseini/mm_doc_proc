@description('Location for the resource')
param location string

@description('Whether to create a new Azure OpenAI resource')
param createOpenAi bool

@description('Name for the Azure OpenAI resource. If createOpenAi=true: The new resource name to create. If createOpenAi=false: Used for reference but no resource is created.')
param openAiResourceName string

@secure()
@description('If NOT creating a new Azure OpenAI resource, supply the existing OpenAI API key here. This value can be set in parameters.json or supplied manually during deployment.')
param existingOpenAiApiKey string = ''

@description('If NOT creating a new Azure OpenAI resource, supply the endpoint, e.g. https://my-openai.openai.azure.com/. This value can be set in parameters.json or supplied manually during deployment.')
param existingOpenAiResource string = ''

@description('GPT-4o deployment name')
param gpt4oDeploymentName string

@description('GPT-4.1 deployment name')
param gpt41DeploymentName string

@description('o1 deployment name')
param o1DeploymentName string

@description('o1-mini deployment name')
param o1MiniDeploymentName string

@description('o3-mini deployment name')
param o3MiniDeploymentName string

@description('Text embedding 3 Large deployment name')
param textEmbedding3LargeDeploymentName string

@description('Tags for the resources')
param tags object = {}

@description('User Assigned Identity Principal ID for access control')
param userAssignedIdentityPrincipalId string

// Validate inputs - ensuring we have either valid new resource config OR valid existing resource config
var inputValidation = {
  hasValidExistingConfig: (!createOpenAi && !empty(existingOpenAiApiKey) && !empty(existingOpenAiResource)) || createOpenAi
  missingNewOpenAiName: createOpenAi && empty(openAiResourceName)
}

// Assert valid configuration
resource assertValidConfig 'Microsoft.Resources/deploymentScripts@2020-10-01' = if (!inputValidation.hasValidExistingConfig) {
  name: 'assertValidOpenAiConfig'
  location: location
  kind: 'AzureCLI'
  properties: {
    azCliVersion: '2.40.0'
    retentionInterval: 'P1D'
    scriptContent: 'echo "Error: When createOpenAi=false, you must provide both existingOpenAiApiKey and existingOpenAiResource" && exit 1'
  }
}

// Assert valid new resource name
resource assertValidNewName 'Microsoft.Resources/deploymentScripts@2020-10-01' = if (inputValidation.missingNewOpenAiName) {
  name: 'assertValidOpenAiName'
  location: location
  kind: 'AzureCLI'
  properties: {
    azCliVersion: '2.40.0'
    retentionInterval: 'P1D'
    scriptContent: 'echo "Error: When createOpenAi=true, you must provide an openAiResourceName" && exit 1'
  }
}

var debugLogs = {
  resourceDetails: 'OpenAI resource details: Name: ${openAiResourceName}, Create new: ${createOpenAi}, Endpoint: ${createOpenAi ? 'https://${openAiResourceName}.openai.azure.com/' : 'https://${existingOpenAiResource}.openai.azure.com/'}'
  modelDeployments: 'Model deployments: GPT-4o: ${gpt4oDeploymentName}, GPT-4.1: ${gpt41DeploymentName}, o1: ${o1DeploymentName}, o1-mini: ${o1MiniDeploymentName}, o3-mini: ${o3MiniDeploymentName}, text-embedding-3-large: ${textEmbedding3LargeDeploymentName}'
}

// // Create the OpenAI resource if specified
// resource newOpenAI 'Microsoft.CognitiveServices/accounts@2023-05-01' = if (createOpenAi) {
//   name: openAiResourceName
//   location: location
//   tags: tags
//   kind: 'OpenAI'
//   sku: {
//     name: 'S0'
//   }
//   properties: {
//     customSubDomainName: openAiResourceName
//     publicNetworkAccess: 'Enabled'
//   }
// }

// Then, reference an existing OpenAI resource when not creating a new one
resource openAI 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (!createOpenAi) {
  name: existingOpenAiResource
}

// // Use a variable to reference the appropriate resource based on condition
// var openAI = createOpenAi ? newOpenAI : existingOpenAI

// Model deployments - only created if we're creating a new OpenAI resource
// When using an existing resource (createOpenAi = false), these deployments are skipped entirely
// as they are assumed to already exist in the referenced resource
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(gpt4oDeploymentName)) {
  parent: openAI
  name: gpt4oDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
    }
  }
}

resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(gpt41DeploymentName)) {
  parent: openAI
  name: gpt41DeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
    }
  }
}

resource o1Deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(o1DeploymentName)) {
  parent: openAI
  name: o1DeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'o1'
    }
  }
}

resource o1MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(o1MiniDeploymentName)) {
  parent: openAI
  name: o1MiniDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'o1-mini'
    }
  }
}

resource o3MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(o3MiniDeploymentName)) {
  parent: openAI
  name: o3MiniDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'o3-mini'
    }
  }
}

resource textEmbedding3LargeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (createOpenAi && !empty(textEmbedding3LargeDeploymentName)) {
  parent: openAI
  name: textEmbedding3LargeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 150
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
    }
  }
}


// Assign the User Assigned Identity Contributor role
resource openAIbAccountRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(openAI.id, userAssignedIdentityPrincipalId, 'Cognitive Services OpenAI User')
  scope: openAI
  properties: {
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Role definition ID for Cognitive Services OpenAI User
    principalId: userAssignedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}



// Construct the endpoint URL based on whether we're creating a new resource or using an existing one
var openAiEndpoint = createOpenAi ? 'https://${openAiResourceName}.openai.azure.com/' : 'https://${existingOpenAiResource}.openai.azure.com/'

// Use the appropriate key - either from the new resource or the provided existing key
var openAiApiKey = createOpenAi ? openAI.listKeys().key1 : existingOpenAiApiKey

// Outputs for reference by other modules
output openAiName string = openAiResourceName
output openAiEndpoint string = openAiEndpoint
output openAiKeyAvailable bool = !empty(openAiApiKey) 
// This indicates whether a key is available, useful for validation in consuming modules

// While we can't use @secure for outputs, we can provide a way for other modules 
// to get the key if needed via module reference
@description('Returns the OpenAI API key if explicitly requested')
output openAiApiKey string = openAiApiKey

// Add debug log output for troubleshooting
output debugLog object = debugLogs
