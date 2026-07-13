"""
Automação de Sprints Semanais - Projeto RAJ
Board ID configurável via variável de ambiente.

Fluxo:
1. Busca a sprint ativa no board
2. Se ela está vencida (endDate <= hoje):
   a. Cria nova sprint (próximo número sequencial + mês/ano atual)
   b. Move issues não concluídas da antiga para a nova
   c. Fecha a sprint antiga
   d. Ativa a nova sprint
3. Se não há sprint vencida, não faz nada
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# ============================================================
# CONFIGURAÇÃO (via variáveis de ambiente)
# ============================================================
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "").strip()
BOARD_ID = os.environ.get("BOARD_ID", "").strip()
DURACAO_SPRINT_DIAS = int(os.environ.get("DURACAO_SPRINT_DIAS", "7"))

# Fuso horário de São Paulo: UTC-3
SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))

# ============================================================
# VALIDAÇÃO
# ============================================================
def validar_config():
    erros = []
    if not JIRA_DOMAIN:
        erros.append("JIRA_DOMAIN não configurado")
    if not JIRA_EMAIL:
        erros.append("JIRA_EMAIL não configurado")
    if not JIRA_API_TOKEN:
        erros.append("JIRA_API_TOKEN não configurado")
    if not BOARD_ID:
        erros.append("BOARD_ID não configurado")
    if erros:
        for e in erros:
            print(f"❌ {e}")
        sys.exit(1)

# ============================================================
# CLIENTE API
# ============================================================
BASE_URL = None
AUTH = None

def setup_api():
    global BASE_URL, AUTH
    BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
    AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

def api_get(endpoint):
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, auth=AUTH, headers={"Accept": "application/json"})
    return resp

def api_post(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    resp = requests.post(url, auth=AUTH, json=data, headers={"Content-Type": "application/json"})
    return resp

def api_put(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    resp = requests.put(url, auth=AUTH, json=data, headers={"Content-Type": "application/json"})
    return resp

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def get_sprints(board_id, state):
    """Busca sprints do board por estado (active, future, closed)."""
    sprints = []
    start = 0
    while True:
        resp = api_get(f"/board/{board_id}/sprint?state={state}&startAt={start}&maxResults=50")
        if resp.status_code != 200:
            print(f"⚠️ Erro ao buscar sprints ({state}): {resp.status_code}")
            break
        data = resp.json()
        sprints.extend(data.get("values", []))
        if data.get("isLast", True):
            break
        start += 50
    return sprints

def extrair_numero_sprint(nome):
    """Extrai o número sequencial do nome da sprint. Ex: 'Sprint 48 - 07/2026' -> 48"""
    import re
    match = re.search(r"Sprint\s+(\d+)", nome)
    if match:
        return int(match.group(1))
    return 0

def get_maior_numero_sprint(board_id):
    """Busca o maior número de sprint existente no board."""
    maior = 0
    for state in ["active", "future", "closed"]:
        sprints = get_sprints(board_id, state)
        for s in sprints:
            num = extrair_numero_sprint(s.get("name", ""))
            if num > maior:
                maior = num
    return maior

def get_issues_pendentes(sprint_id):
    """Retorna lista de issue keys não concluídas de uma sprint."""
    issues_pendentes = []
    start = 0
    while True:
        resp = api_get(f"/sprint/{sprint_id}/issue?startAt={start}&maxResults=100&fields=status")
        if resp.status_code != 200:
            print(f"⚠️ Erro ao buscar issues da sprint {sprint_id}: {resp.status_code}")
            break
        data = resp.json()
        for issue in data.get("issues", []):
            status_category = issue["fields"]["status"]["statusCategory"]["key"]
            if status_category != "done":
                issues_pendentes.append(issue["key"])
        if start + 100 >= data.get("total", 0):
            break
        start += 100
    return issues_pendentes

# ============================================================
# FLUXO PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL")
    print("=" * 60)

    validar_config()
    setup_api()

    agora = datetime.now(SAO_PAULO_OFFSET)
    hoje_str = agora.strftime("%Y-%m-%d")
    print(f"\n📅 Data atual (São Paulo): {agora.strftime('%d/%m/%Y %H:%M')}")
    print(f"📋 Board ID: {BOARD_ID}")
    print(f"⏱️ Duração da sprint: {DURACAO_SPRINT_DIAS} dias")

    # 1. Buscar sprints ativas
    print("\n🔍 Buscando sprints ativas...")
    sprints_ativas = get_sprints(BOARD_ID, "active")

    if not sprints_ativas:
        print("ℹ️ Nenhuma sprint ativa encontrada.")
        print("   Criando nova sprint do zero...")
        # Cria e ativa uma sprint nova
        criar_e_ativar_nova_sprint(agora, None)
        return

    # 2. Verificar se alguma sprint ativa está vencida
    sprint_vencida = None
    for sprint in sprints_ativas:
        end_date_str = sprint.get("endDate", "")
        if not end_date_str:
            continue
        # A API retorna formato ISO: "2026-07-13T..."
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        # Converter para São Paulo para comparar
        end_date_sp = end_date.astimezone(SAO_PAULO_OFFSET).date()
        hoje_date = agora.date()

        print(f"\n📌 Sprint ativa: {sprint['name']} (ID: {sprint['id']})")
        print(f"   Data fim: {end_date_sp.strftime('%d/%m/%Y')}")
        print(f"   Hoje: {hoje_date.strftime('%d/%m/%Y')}")

        if end_date_sp <= hoje_date:
            print(f"   ⚠️ VENCIDA! Processando...")
            sprint_vencida = sprint
            break
        else:
            print(f"   ✅ Ainda vigente. Nada a fazer.")

    if not sprint_vencida:
        print("\n✅ Nenhuma sprint vencida. Automação finalizada sem alterações.")
        return

    # 3. Processar sprint vencida
    criar_e_ativar_nova_sprint(agora, sprint_vencida)

def criar_e_ativar_nova_sprint(agora, sprint_vencida):
    """Cria nova sprint, move issues, fecha antiga, ativa nova."""

    # Calcular próximo número
    maior_numero = get_maior_numero_sprint(BOARD_ID)
    proximo_numero = maior_numero + 1
    mes_atual = agora.strftime("%m")
    ano_atual = agora.strftime("%Y")
    nome_nova = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    # Datas da nova sprint
    data_inicio = agora.strftime("%Y-%m-%d")
    data_fim = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%d")

    print(f"\n📝 Criando: {nome_nova}")
    print(f"   Início: {data_inicio} | Fim: {data_fim}")

    # 4. CRIAR nova sprint (estado future)
    payload_criar = {
        "name": nome_nova,
        "originBoardId": int(BOARD_ID),
        "goal": "Sprint criada automaticamente"
    }

    resp = api_post("/sprint", payload_criar)
    if resp.status_code not in [200, 201]:
        print(f"❌ Erro ao criar sprint: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        sys.exit(1)

    nova_sprint = resp.json()
    nova_sprint_id = nova_sprint["id"]
    print(f"   ✅ Sprint criada! ID: {nova_sprint_id}")

    # 5. MOVER issues pendentes (se houver sprint vencida)
    if sprint_vencida:
        print(f"\n🔄 Buscando issues pendentes da {sprint_vencida['name']}...")
        issues_pendentes = get_issues_pendentes(sprint_vencida["id"])

        if issues_pendentes:
            print(f"   📦 {len(issues_pendentes)} issues para mover: {', '.join(issues_pendentes)}")

            # Mover em lotes de 50
            for i in range(0, len(issues_pendentes), 50):
                lote = issues_pendentes[i:i+50]
                payload_mover = {"issues": lote}
                resp_mover = api_post(f"/sprint/{nova_sprint_id}/issue", payload_mover)
                if resp_mover.status_code in [200, 204]:
                    print(f"   ✅ Lote movido: {len(lote)} issues")
                else:
                    print(f"   ❌ Erro ao mover lote: {resp_mover.status_code}")
                    print(f"      Resposta: {resp_mover.text}")
        else:
            print(f"   ℹ️ Nenhuma issue pendente para mover.")

        # 6. FECHAR sprint vencida
        print(f"\n🔒 Fechando {sprint_vencida['name']}...")
        payload_fechar = {
            "state": "closed"
        }
        resp_fechar = api_put(f"/sprint/{sprint_vencida['id']}", payload_fechar)
        if resp_fechar.status_code == 200:
            print(f"   ✅ Sprint fechada com sucesso!")
        else:
            print(f"   ❌ Erro ao fechar: {resp_fechar.status_code}")
            print(f"      Resposta: {resp_fechar.text}")
            # Tenta com completeDate como fallback
            print(f"   🔄 Tentando com completeDate...")
            payload_fechar2 = {
                "state": "closed",
                "completeDate": agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
            }
            resp_fechar2 = api_put(f"/sprint/{sprint_vencida['id']}", payload_fechar2)
            if resp_fechar2.status_code == 200:
                print(f"   ✅ Sprint fechada (com completeDate)!")
            else:
                print(f"   ❌ Falha definitiva ao fechar: {resp_fechar2.status_code}")
                print(f"      Resposta: {resp_fechar2.text}")
                print(f"   ⚠️ Continuando mesmo assim para ativar a nova sprint...")

    # 7. ATIVAR nova sprint
    print(f"\n▶️ Ativando {nome_nova}...")
    payload_ativar = {
        "state": "active",
        "startDate": f"{data_inicio}T08:00:00.000-03:00",
        "endDate": f"{data_fim}T08:00:00.000-03:00"
    }
    resp_ativar = api_put(f"/sprint/{nova_sprint_id}", payload_ativar)
    if resp_ativar.status_code == 200:
        print(f"   ✅ Sprint ativada com sucesso!")
    else:
        print(f"   ❌ Erro ao ativar: {resp_ativar.status_code}")
        print(f"      Resposta: {resp_ativar.text}")
        sys.exit(1)

    # 8. RESUMO FINAL
    print("\n" + "=" * 60)
    print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 60)
    if sprint_vencida:
        print(f"   Sprint fechada: {sprint_vencida['name']}")
    print(f"   Sprint criada e ativada: {nome_nova}")
    if sprint_vencida:
        issues_pendentes = get_issues_pendentes(sprint_vencida["id"]) if sprint_vencida else []
        print(f"   Issues movidas: {len(issues_pendentes) if sprint_vencida else 0}")
    print(f"   Próxima execução: próxima segunda-feira")
    print("=" * 60)

if __name__ == "__main__":
    main()
