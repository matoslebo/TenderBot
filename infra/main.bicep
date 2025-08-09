param location string = resourceGroup().location
param acrName string = 'tendersenseacr'
param envName string = 'ts-env'
param laName string = 'ts-law'
param appInsightsName string = 'ts-ai'

resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  identity: { type: 'SystemAssigned' }
}

resource la 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: laName
  location: location
  sku: { name: 'PerGB2018' }
  properties: {
    retentionInDays: 30
    features: { searchVersion: 1 }
  }
}

resource ai 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: la.id
  }
}

var laCustomerId = la.properties.customerId
var laSharedKey  = listKeys(la.id, '2020-08-01').primarySharedKey

resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: laCustomerId
        sharedKey: laSharedKey
      }
    }
  }
}

output acrLoginServer string = acr.properties.loginServer
output envName        string = env.name
output laCustomerId   string = laCustomerId
