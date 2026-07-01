# Central de Monitoramento

Módulo operacional para acompanhamento de escolas de São Paulo e Ceará nas
plataformas Omada, Zyxel e Ubiquiti.

## Fontes e regras

- **Omada:** recebe `.xlsx`; usa `Last Uptime` como início da indisponibilidade.
- **Zyxel:** recebe `.csv`; como o arquivo não informa o início da queda, o
  primeiro upload offline inicia o contador e uploads posteriores preservam esse horário.
- **Ubiquiti:** consulta as contas selecionadas e usa `Último Sinal` quando disponível.
- Somente INEPs iniciados por `35` (SP) ou `23` (CE) entram no módulo.
- O SLA operacional é de quatro horas.
- Zyxel com todos os dispositivos fora é `Offline total`; indisponibilidade
  parcial é `Degradada`.
- `Obras`, `Renegociação de Link` e `Inviabilidade de Link` permanecem visíveis,
  mas são classificadas como exceção e não entram nas métricas de SLA.

## Segurança

A senha padrão solicitada não fica gravada em texto aberto no repositório.
Para substituir a senha, configure no `secrets.toml`:

```toml
[monitoring]
password = "sua-senha"
```

O acesso ao Hub continua sendo exigido antes da autenticação específica do módulo.

## Persistência no Supabase

Execute [`supabase/monitoring.sql`](../supabase/monitoring.sql) uma vez no SQL
Editor do projeto Supabase. O módulo utilizará as credenciais já configuradas
no Hub.

Opcionalmente, personalize o nome da tabela:

```toml
[supabase]
monitoring_table = "hub_monitoring_state"
```

Enquanto a tabela não existir, o sistema usa `data/monitoring_state.json`. Esse
arquivo é ignorado pelo Git e serve como contingência local; em hospedagens
efêmeras, o Supabase é obrigatório para não perder o histórico.

## Fluxo recomendado

1. Selecione os exports Omada e Zyxel mais recentes.
2. Clique em `Atualizar monitoramento`; a consulta Ubiquiti de SP/CE ocorre automaticamente.
3. Abra `Ação necessária` e atenda da ocorrência mais antiga para a mais recente.
4. Registre o número do chamado e a etapa do atendimento.
5. Cadastre o nome oficial da escola e o gestor antes de abrir o WhatsApp.
6. Use a fila de contatos em massa uma conversa por vez.
7. Revise `Pendências dos dados` para conflitos, registros ausentes e linhas ignoradas.

## Cadastro escolar

Os exports informam INEP e município, mas não trazem o nome oficial da escola.
Esse nome pode ser cadastrado no card e fica associado ao INEP. Para carga em
massa, será necessário fornecer uma base com, no mínimo:

- INEP
- nome oficial da escola
- município
- UF
