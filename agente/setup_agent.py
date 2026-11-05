# Crea el conocimiento (vector store con 4 documentos) y el agente "nutribot" en Foundry
import glob, os, sys
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FileSearchTool

EP = "https://loreniaorantes-ia-2392-resource.services.ai.azure.com/api/projects/loreniaorantes-ia-2392"
project = AIProjectClient(endpoint=EP, credential=DefaultAzureCredential())
oai = project.get_openai_client()

vs = oai.vector_stores.create(name="conocimiento-nutrionix")
for path in sorted(glob.glob("conocimiento/*.md")):
    with open(path, "rb") as f:
        r = oai.vector_stores.files.upload_and_poll(vector_store_id=vs.id, file=f)
    print("archivo:", os.path.basename(path), r.status)

agent = project.agents.create_version(
    agent_name="nutribot",
    description="Asistente de IA de Producción y Costos de Nutrionix (Fase 2)",
    definition=PromptAgentDefinition(
        model="gpt-5.4-mini",
        instructions=open("instrucciones_agente.txt", encoding="utf-8").read(),
        tools=[FileSearchTool(vector_store_ids=[vs.id])],
    ),
)
print("AGENTE:", agent.name, "version", agent.version)

r = oai.responses.create(
    input="¿Qué productos superaron su presupuesto en octubre?",
    extra_body={"agent_reference": {"name": "nutribot", "type": "agent_reference"}},
)
print("PRUEBA:", r.output_text[:600])
