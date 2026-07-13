# 🚀 Automação de Sprint Semanal - Jira Cloud

Automação que roda toda **segunda-feira às 08:00 (Brasília)** via GitHub Actions.

## O que faz

1. ✅ Identifica a sprint ativa que já venceu
2. ✅ Cria uma nova sprint com nomenclatura sequencial (`Sprint XX - MM/AAAA`)
3. ✅ Move issues não concluídas da sprint vencida para a nova
4. ✅ Fecha a sprint vencida
5. ✅ Ativa a nova sprint

## Configuração Rápida

### 1. Gerar API Token do Jira

1. Acesse: https://id.atlassian.com/manage-profile/security/api-tokens
2. Clique em **"Create API token"**
3. Nome: `Sprint Automation`
4. Copie o token gerado (ele não será mostrado novamente!)

### 2. Configurar Secrets no GitHub

No seu repositório, vá em **Settings → Secrets and variables → Actions → New repository secret**

Crie estes 4 secrets:

| Secret Name | Valor |
|-------------|-------|
| `JIRA_DOMAIN` | `grazziotin-sa.atlassian.net` |
| `JIRA_EMAIL` | Seu email do Jira (ex: `eduardo@grazziotin.com.br`) |
| `JIRA_API_TOKEN` | O token gerado no passo anterior |
| `BOARD_ID` | `89` |

### 3. Estrutura do Repositório

```
seu-repositorio/
├── .github/
│   └── workflows/
│       └── sprint_semanal.yml
├── sprint_automation.py
├── requirements.txt
└── README.md
```

### 4. Testar Manualmente

1. Vá na aba **Actions** do repositório
2. Clique em **"Sprint Semanal - RAJ"** na barra lateral
3. Clique em **"Run workflow"** → **"Run workflow"**
4. Acompanhe a execução nos logs

## Personalização

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `BOARD_ID` | `89` | ID do board no Jira |
| `DURACAO_SPRINT_DIAS` | `7` | Duração da sprint em dias |
| Cron schedule | `0 11 * * 1` | Segunda 08:00 BRT (11:00 UTC) |

## Nomenclatura das Sprints

O padrão segue: `Sprint {número_sequencial} - {mês}/{ano}`

Exemplos:
- Sprint 48 - 07/2026
- Sprint 49 - 07/2026
- Sprint 50 - 08/2026 (mês muda automaticamente)

## Troubleshooting

| Erro | Solução |
|------|---------|
| `401 Unauthorized` | Verifique email e API token nos secrets |
| `403 Forbidden` | Seu usuário precisa ter permissão de admin no board |
| `404 Not Found` | Verifique se o BOARD_ID está correto |
| Sprint não ativa | Pode haver outra sprint ativa; o Jira permite apenas 1 por board |

## Custos

**$0** — GitHub Actions oferece 2.000 minutos/mês grátis para repositórios privados.
Este script usa menos de 1 minuto por execução semanal (~4 min/mês).
