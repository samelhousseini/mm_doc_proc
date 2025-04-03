@description('Location for the resource')
param location string

@description('Container Apps Environment name')
param environmentName string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string = ''

@description('Container Apps Job name')
param jobName string

@description('ACR Login Server')
param acrLoginServer string

@description('Image name and tag')
param imageName string

@description('Maximum number of parallel job executions')
@minValue(1)
@maxValue(20)
param maxParallelExecutions int

@description('Minimum number of executions (0 for scale to zero)')
@allowed([0, 1])
param minExecutions int

@description('CPU cores allocated to the job container')
param containerCpuCores string

@description('Memory allocated to the job container in gigabytes')
param containerMemoryGb string

@description('Managed Identity ID')
param managedIdentityId string

@description('Environment variables for the container')
param environmentVariables array

@description('Tags to apply to resources')
param tags object

@description('Secrets for the job')
param secrets array = []

@description('Rules for scaling the job')
param eventRules array = []

var debugInfo = {
  environment: environmentName
  jobName: jobName
  image: '${acrLoginServer}/${imageName}'
  parallelExecutions: maxParallelExecutions
  resources: '${containerCpuCores} CPU, ${containerMemoryGb}GB Memory'
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-04-01-preview' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: !empty(logAnalyticsWorkspaceId) ? reference(logAnalyticsWorkspaceId, '2022-10-01').customerId : ''
        sharedKey: !empty(logAnalyticsWorkspaceId) ? listKeys(logAnalyticsWorkspaceId, '2022-10-01').primarySharedKey : ''
      }
    }
  }
}

resource containerAppJob 'Microsoft.App/jobs@2023-04-01-preview' = {
  name: jobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      secrets: secrets
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
      triggerType: 'Event' //'Event'
      replicaTimeout: 18000 // 5 hours
      manualTriggerConfig: {
        parallelism: maxParallelExecutions
        replicaCompletionCount: 1
      }
      eventTriggerConfig: {
        parallelism: maxParallelExecutions
        replicaCompletionCount: 1
        scale: {
          minExecutions: minExecutions
          maxExecutions: maxParallelExecutions
          pollingInterval: 30
          rules: eventRules
        }
      }
      scheduleTriggerConfig: null
      replicaRetryLimit: 1
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/${imageName}'
          name: 'document-processor'
          resources: {
            cpu: json(containerCpuCores)
            memory: '${containerMemoryGb}Gi'
          }
          env: environmentVariables
        }
      ]
    }
  }
}

// Diagnostic Settings
resource envDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'containerEnvDiag'
  scope: containerAppsEnvironment
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'ContainerAppConsoleLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output containerAppsEnvironmentName string = containerAppsEnvironment.name
output containerAppsEnvironmentId string = containerAppsEnvironment.id
output containerAppsJobName string = containerAppJob.name
output containerAppsJobId string = containerAppJob.id
output debugLogs object = debugInfo
