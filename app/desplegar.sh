#!/bin/bash
# =====================================================================
#  NutriBot (Nutrionix Fase 2) – Despliegue en Azure App Service
#  Ejecutar en Azure Cloud Shell (Bash), DENTRO de la carpeta "app".
#  Antes: edita SOLO las 5 variables de abajo.
# =====================================================================
set -e

RG="rg-loreniaorantes-ia-1040"
FOUNDRY_RESOURCE="loreniaorantes-ia-2392-resource"
PROJECT_ENDPOINT="https://loreniaorantes-ia-2392-resource.services.ai.azure.com/api/projects/loreniaorantes-ia-2392"
AGENT_NAME="nutribot"             # nombre exacto del agente en Foundry
APP_NAME="nutribot-lorenia"       # nombre único en todo Azure -> será https://APP_NAME.azurewebsites.net
LOCATION="canadacentral"
SKU="F1"                          # F1 = gratis. Si marca error de cuota, usa B1

echo "1/5 Creando y publicando la app web (tarda 3-6 min)..."
az webapp up --name "$APP_NAME" --resource-group "$RG" --location "$LOCATION" \
  --runtime "PYTHON:3.12" --sku "$SKU"

echo "2/5 Comando de arranque..."
az webapp config set -g "$RG" -n "$APP_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 180 app:app" > /dev/null

echo "3/5 Variables de configuración..."
az webapp config appsettings set -g "$RG" -n "$APP_NAME" --settings \
  PROJECT_ENDPOINT="$PROJECT_ENDPOINT" AGENT_NAME="$AGENT_NAME" \
  FLASK_SECRET="$(openssl rand -hex 24)" SCM_DO_BUILD_DURING_DEPLOYMENT=true > /dev/null

echo "4/5 Identidad administrada + permiso "Foundry User" sobre Foundry..."
PRINCIPAL_ID=$(az webapp identity assign -g "$RG" -n "$APP_NAME" --query principalId -o tsv)
FOUNDRY_ID=$(az cognitiveservices account show -g "$RG" -n "$FOUNDRY_RESOURCE" --query id -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role "Foundry User" --scope "$FOUNDRY_ID" > /dev/null

echo "5/5 Reiniciando..."
az webapp restart -g "$RG" -n "$APP_NAME"

echo ""
echo "LISTO -> https://$APP_NAME.azurewebsites.net"
echo "(Si la primera pregunta marca error de permisos, espera 5-10 min: el rol tarda en propagarse.)"
