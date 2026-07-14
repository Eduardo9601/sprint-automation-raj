import os
import re
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# CONFIGURAÇÃO
# ============================================================
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")

AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
BASE_URL_V2 = f"https://{JIRA_DOMAIN}/rest/api/2"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

FUSO_BR = timezone(timedelta(hours=-3))


# ============================================================
# FUNÇÕES AUXILIARES - JIRA
# ============================================================
def obter_todas_sprints(board_id, states="active,closed,future"):
    """Obtém TODAS as sprints do board com paginação completa."""
    sprints = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/board/{board_id}/sprint?state={states}&startAt={start_at}&maxResults={max_results}"
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        sprints.extend(data.get("values", []))

        if data.get("isLast", True):
            break
        start_at += max_results

    return sprints


def obter_sprint_ativa(board_id):
    """Retorna a sprint ativa do board."""
    url = f"{BASE_URL}/board/{board_id}/sprint?state=active"
    response = requests.get(url, auth=AUTH, headers=HEADERS)
    response.raise_for_status()
    sprints = response.json().get("values", [])
    return sprints[0] if sprints else None


def obter_issues_sprint(sprint_id):
    """Obtém todas as issues de uma sprint."""
    issues = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/sprint/{sprint_id}/issue?startAt={start_at}&maxResults={max_results}"
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        issues.extend(data.get("issues", []))

        if start_at + max_results >= data.get("total", 0):
            break
        start_at += max_results

    return issues


def obter_proximo_numero_sprint(board_id):
    """Descobre o próximo número da sprint baseado no histórico completo."""
    todas_sprints = obter_todas_sprints(board_id)
    maior_numero = 0

    for sprint in todas_sprints:
        nome = sprint.get("name", "")
        match = re.search(r"Sprint\s+(\d+)", nome)
        if match:
            numero = int(match.group(1))
            if numero > maior_numero:
                maior_numero = numero

    return maior_numero + 1


def criar_sprint(board_id, nome, start_date, end_date):
    """Cria uma nova sprint no board."""
    url = f"{BASE_URL}/sprint"
    payload = {
        "name": nome,
        "startDate": start_date,
        "endDate": end_date,
        "originBoardId": int(board_id),
        "goal": f"Sprint criada automaticamente em {datetime.now(FUSO_BR).strftime('%d/%m/%Y')}"
    }
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def mover_issues_para_sprint(sprint_id, issue_keys):
    """Move issues para uma sprint."""
    if not issue_keys:
        return
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    payload = {"issues": issue_keys}
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()


def fechar_sprint(sprint_id):
    """Fecha (completa) uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {"state": "closed"}
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()


def ativar_sprint(sprint_id):
    """Ativa uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {"state": "active"}
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    response.raise_for_status()


# ============================================================
# FUNÇÕES - RELATÓRIO MARKDOWN (GITHUB)
# ============================================================
def gerar_relatorio_markdown(sprint_fechada, sprint_nova, issues_concluidas, issues_movidas):
    """Gera o conteúdo do relatório em Markdown."""
    agora = datetime.now(FUSO_BR).strftime("%d/%m/%Y às %H:%M")
    total = len(issues_concluidas) + len(issues_movidas)
    percentual = round((len(issues_concluidas) / total) * 100) if total > 0 else 0

    md = f"""# 📋 Relatório Sprint - {sprint_fechada['name']}

**📅 Gerado em:** {agora}
**🏁 Sprint encerrada:** {sprint_fechada['name']}
**🆕 Sprint iniciada:** {sprint_nova['name']}
**📊 Taxa de conclusão:** {percentual}% ({len(issues_concluidas)} de {total} tarefas)

---

## ✅ Tarefas Finalizadas ({len(issues_concluidas)})

| Chave | Título | Tipo | Responsável |
|-------|--------|------|-------------|
"""

    for issue in issues_concluidas:
        key = issue["key"]
        titulo = issue["fields"]["summary"]
        tipo = issue["fields"]["issuetype"]["name"]
        responsavel = issue["fields"].get("assignee", {})
        nome_responsavel = responsavel.get("displayName", "Não atribuído") if responsavel else "Não atribuído"
        link = f"[{key}](https://{JIRA_DOMAIN}/browse/{key})"
        md += f"| {link} | {titulo} | {tipo} | {nome_responsavel} |\n"

    md += f"""
---

## 🔄 Tarefas Transferidas para {sprint_nova['name']} ({len(issues_movidas)})

| Chave | Título | Tipo | Responsável | Status |
|-------|--------|------|-------------|--------|
"""

    for issue in issues_movidas:
        key = issue["key"]
        titulo = issue["fields"]["summary"]
        tipo = issue["fields"]["issuetype"]["name"]
        status = issue["fields"]["status"]["name"]
        responsavel = issue["fields"].get("assignee", {})
        nome_responsavel = responsavel.get("displayName", "Não atribuído") if responsavel else "Não atribuído"
        link = f"[{key}](https://{JIRA_DOMAIN}/browse/{key})"
        md += f"| {link} | {titulo} | {tipo} | {nome_responsavel} | {status} |\n"

    md += f"""
---

## 📊 Resumo

- **Total de tarefas na sprint:** {total}
- **Concluídas:** {len(issues_concluidas)} ✅
- **Transferidas:** {len(issues_movidas)} 🔄
- **Taxa de conclusão:** {percentual}%

---

> *Relatório gerado automaticamente pelo Sprint Bot*
"""

    return md


def salvar_relatorio_github(sprint_fechada, conteudo_md):
    """Salva o relatório como arquivo .md no repositório via GitHub API."""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("⚠️ GITHUB_TOKEN ou GITHUB_REPOSITORY não configurados. Pulando relatório.")
        return

    agora = datetime.now(FUSO_BR)
    nome_arquivo = f"relatorios/sprint_{sprint_fechada['name'].replace(' ', '_').replace('/', '-')}_{agora.strftime('%Y-%m-%d')}.md"

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{nome_arquivo}"
    headers_gh = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    import base64
    conteudo_b64 = base64.b64encode(conteudo_md.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"📋 Relatório: {sprint_fechada['name']} - {agora.strftime('%d/%m/%Y')}",
        "content": conteudo_b64,
        "branch": "main"
    }

    response = requests.put(url, headers=headers_gh, json=payload)

    if response.status_code in [200, 201]:
        print(f"✅ Relatório salvo no repositório: {nome_arquivo}")
    else:
        print(f"⚠️ Erro ao salvar relatório no GitHub: {response.status_code} - {response.text}")


# ============================================================
# FUNÇÕES - NOTIFICAÇÃO TEAMS (ADAPTIVE CARD)
# ============================================================
def enviar_notificacao_teams(sprint_fechada, sprint_nova, issues_concluidas, issues_movidas):
    """Envia o resumo semanal para o Teams via Adaptive Card."""
    if not TEAMS_WEBHOOK_URL:
        print("ℹ️ TEAMS_WEBHOOK_URL não configurado. Pulando notificação Teams.")
        return

    agora = datetime.now(FUSO_BR).strftime("%d/%m/%Y às %H:%M")
    total = len(issues_concluidas) + len(issues_movidas)
    percentual = round((len(issues_concluidas) / total) * 100) if total > 0 else 0

    # Montar lista de concluídas com links
    lista_concluidas = ""
    for issue in issues_concluidas:
        key = issue["key"]
        titulo = issue["fields"]["summary"]
        lista_concluidas += f"- ✅ [{key}](https://{JIRA_DOMAIN}/browse/{key}) — {titulo}\n"

    if not lista_concluidas:
        lista_concluidas = "- Nenhuma tarefa finalizada nesta sprint\n"

    # Montar lista de transferidas com links
    lista_movidas = ""
    for issue in issues_movidas:
        key = issue["key"]
        titulo = issue["fields"]["summary"]
        lista_movidas += f"- 🔄 [{key}](https://{JIRA_DOMAIN}/browse/{key}) — {titulo}\n"

    if not lista_movidas:
        lista_movidas = "- Nenhuma tarefa transferida\n"

    # Adaptive Card
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🏁 Sprint Concluída: {sprint_fechada['name']}",
                            "weight": "Bolder",
                            "size": "Large",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"📅 {agora} | 📊 {percentual}% concluído ({len(issues_concluidas)} de {total})",
                            "size": "Small",
                            "isSubtle": True,
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**✅ Tarefas Finalizadas ({len(issues_concluidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Medium",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_concluidas,
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**🔄 Transferidas → {sprint_nova['name']} ({len(issues_movidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Medium",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_movidas,
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"---\n📊 **Resumo:** {len(issues_concluidas)} concluídas | {len(issues_movidas)} transferidas | {percentual}% de conclusão",
                            "wrap": True,
                            "spacing": "Medium"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "📋 Ver Board no Jira",
                            "url": f"https://{JIRA_DOMAIN}/jira/software/c/projects/RAJ/boards/{BOARD_ID}"
                        }
                    ]
                }
            }
        ]
    }

    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, headers={"Content-Type": "application/json"})
        if response.status_code in [200, 202]:
            print("✅ Notificação enviada para o Teams com sucesso!")
        else:
            print(f"⚠️ Erro ao enviar para Teams: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"⚠️ Falha ao enviar notificação Teams: {e}")


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("🚀 SPRINT AUTOMATION - RAJ")
    print(f"📅 Execução: {datetime.now(FUSO_BR).strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    # Verificar configuração
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
        print("❌ Erro: Variáveis de ambiente obrigatórias não configuradas!")
        sys.exit(1)

    # 1. Obter sprint ativa
    sprint_ativa = obter_sprint_ativa(BOARD_ID)

    if not sprint_ativa:
        print("ℹ️ Nenhuma sprint ativa encontrada. Nenhuma ação necessária.")
        return

    print(f"✅ Sprint ativa encontrada: {sprint_ativa['name']}")
    print(f"   ID: {sprint_ativa['id']}")
    print(f"   Início: {sprint_ativa.get('startDate', 'N/A')}")
    print(f"   Fim: {sprint_ativa.get('endDate', 'N/A')}")

    # 2. Verificar se a sprint venceu
    end_date_str = sprint_ativa.get("endDate", "")
    if not end_date_str:
        print("⚠️ Sprint ativa não tem data de fim definida. Nenhuma ação.")
        return

    # Parse da data de fim (formato ISO 8601)
    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
    agora = datetime.now(timezone.utc)

    if end_date > agora:
        dias_restantes = (end_date - agora).days
        print(f"ℹ️ Sprint ainda não venceu. Faltam {dias_restantes} dia(s).")
        print("   Nenhuma ação necessária.")
        return

    print(f"⏰ Sprint vencida! Iniciando processo de rotação...")

    # 3. Obter issues da sprint ativa
    issues = obter_issues_sprint(sprint_ativa["id"])
    print(f"📋 Total de issues na sprint: {len(issues)}")

    # Separar concluídas vs pendentes
    issues_concluidas = []
    issues_pendentes = []

    for issue in issues:
        status_category = issue["fields"]["status"]["statusCategory"]["key"]
        if status_category == "done":
            issues_concluidas.append(issue)
        else:
            issues_pendentes.append(issue)

    print(f"   ✅ Concluídas: {len(issues_concluidas)}")
    print(f"   🔄 Pendentes (serão movidas): {len(issues_pendentes)}")

    # 4. Criar nova sprint
    proximo_numero = obter_proximo_numero_sprint(BOARD_ID)
    agora_br = datetime.now(FUSO_BR)
    mes_ano = agora_br.strftime("%m/%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_ano}"

    # Datas da nova sprint (7 dias)
    inicio_nova = agora_br.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
    fim_nova = (agora_br + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

    print(f"\n🆕 Criando: {nome_nova_sprint}")
    nova_sprint = criar_sprint(BOARD_ID, nome_nova_sprint, inicio_nova, fim_nova)
    print(f"   ✅ Sprint criada com ID: {nova_sprint['id']}")

    # 5. Mover issues pendentes para nova sprint
    if issues_pendentes:
        issue_keys = [issue["key"] for issue in issues_pendentes]
        print(f"\n🔄 Movendo {len(issue_keys)} issues para {nome_nova_sprint}...")
        mover_issues_para_sprint(nova_sprint["id"], issue_keys)
        print(f"   ✅ Issues movidas: {', '.join(issue_keys)}")

    # 6. Fechar sprint antiga
    print(f"\n🏁 Fechando sprint: {sprint_ativa['name']}...")
    fechar_sprint(sprint_ativa["id"])
    print(f"   ✅ Sprint fechada!")

    # 7. Ativar nova sprint
    print(f"\n▶️ Ativando sprint: {nome_nova_sprint}...")
    ativar_sprint(nova_sprint["id"])
    print(f"   ✅ Sprint ativada!")

    # 8. Enviar notificação Teams
    print(f"\n📨 Enviando notificação Teams...")
    enviar_notificacao_teams(sprint_ativa, nova_sprint, issues_concluidas, issues_pendentes)

    # 9. Salvar relatório no repositório
    print(f"\n📄 Gerando relatório Markdown...")
    relatorio_md = gerar_relatorio_markdown(sprint_ativa, nova_sprint, issues_concluidas, issues_pendentes)
    salvar_relatorio_github(sprint_ativa, relatorio_md)

    # Resumo final
    print("\n" + "=" * 60)
    print("🎉 PROCESSO CONCLUÍDO COM SUCESSO!")
    print(f"   🏁 Sprint fechada: {sprint_ativa['name']}")
    print(f"   🆕 Sprint ativa: {nome_nova_sprint}")
    print(f"   ✅ Concluídas: {len(issues_concluidas)}")
    print(f"   🔄 Transferidas: {len(issues_pendentes)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
