
param location string = resourceGroup().location
param acrName string = 'tendersenseacr'
param envName string = 'ts-env'

resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  identity: { type: 'SystemAssigned' }
}

resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
    }
  }
}

output acrLoginServer string = acr.properties.loginServer
output envName string = env.name
