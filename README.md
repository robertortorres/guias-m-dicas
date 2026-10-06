# Guias médicas — versão inicial para rede local

Aplicação web em Docker: login, upload de PDF, OCR local em português, sugestão de separação, revisão visual e download em ZIP. Não exige ChatGPT Plus nem chave de API. Os documentos não são enviados a serviços de IA.

## Instalação

No servidor Linux com Docker Engine e Compose:

```bash
unzip guias-medicas.zip
cd guias-medicas
cp .env.example .env
nano .env
# Preencha APP_PASSWORD com uma senha de pelo menos 12 caracteres.
docker compose up -d --build
```

Abra `http://IP_DO_SERVIDOR:8080` na rede e entre com o usuário definido em `.env`. A primeira construção precisa de internet para baixar imagem, bibliotecas e idiomas do OCR. Depois, a leitura funciona localmente.

## Uso

1. Escolha o modo e envie o PDF.
2. Aguarde o OCR. O processamento é sequencial; lotes grandes podem demorar.
3. Confira cada grupo com a imagem das páginas. Corrija número e nome completo.
4. Corrija as páginas dos grupos escrevendo números separados por vírgulas. Para dividir, adicione grupo e mova suas páginas; para juntar, reúna as páginas no grupo e remova o grupo vazio.
5. Marque que conferiu cada documento e baixe o ZIP. O sistema exige que todas as páginas apareçam exatamente uma vez.

| Modo | Conteúdo por arquivo | Nome |
|---|---|---|
| Somente guias | Uma guia | `123456 Ana Vieira.pdf` |
| Guias e pedidos | Guia com suas páginas de pedido | `123456 Pedido Médico Ana Vieira.pdf` |
| Guias, pedidos e laudos | Guia, pedidos e laudos | `123456 Pedido Médico Ana Vieira.pdf` |

Usa primeiro e último termo do nome completo. Nomes repetidos recebem sufixo `(2)` para evitar sobrescrita. As páginas exportadas preservam a digitalização original; a correção de orientação é usada no OCR e na visualização.

## O que está automatizado e o que precisa de revisão

Esta é uma versão inicial assistida, não uma separação garantida sem intervenção. GEAP e Porto usam campos e orientações diferentes. O reconhecimento é baseado em OCR e rótulos dos formulários, e pode confundir números ou deixar campos vazios. O número buscado inicialmente é o da guia no prestador; confirme com a convenção da empresa, especialmente quando o número da operadora for diferente.

No modo somente guias, cada página vira uma sugestão de documento. Guias com várias páginas devem ser unidas durante a revisão. Nos outros modos, cada página reconhecida como guia inicia um grupo; páginas seguintes são anexadas até a próxima guia. Uma guia não reconhecida pode entrar no grupo anterior. O primeiro documento sem guia também inicia um grupo para que nenhuma página desapareça.

**Não há verificação automática de identidade entre guia, pedido e laudo.** Documentos fora de ordem, anexos de outro paciente e pedidos manuscritos exigem conferência visual. Os modos 2 e 3 usam a mesma regra de sequência; a distinção é a expectativa do conteúdo. Tesseract lê texto impresso e não reconhece manuscritos com confiabilidade.

## Operação

```bash
docker compose logs --tail=100
docker compose down
# Reiniciar após mudar configuração:
docker compose up -d --build
```

Limites iniciais: 100 MB por upload, 400 páginas, três lotes em processamento/fila, um OCR por vez, 2 GB RAM. Todos que usam o login compartilham os lotes. Não há histórico persistente: reiniciar o serviço descarta os lotes e invalida sessões. Lotes concluídos são apagados após 24 horas, verificadas a cada minuto; o botão Excluir lote apaga imediatamente.

Para acesso restrito, ajuste `APP_BIND_IP` para o IP da rede interna e restrinja a porta no firewall. Para uso regular com dados de pacientes, coloque atrás do proxy HTTPS da empresa; com HTTPS, defina `COOKIE_SECURE=1`. Não exponha diretamente à internet. Há cookies HttpOnly, proteção CSRF, senha obrigatória e ausência de registros do conteúdo médico, mas não há contas individuais, auditoria ou criptografia do volume nesta versão.

## Validação desta entrega

Testes automatizados cobrem extração de campos, agrupamento, nomenclatura e rejeição de páginas duplicadas ou ausentes. Também foi exercitado o fluxo HTTP de login, upload, processamento e exportação. Os anexos fornecidos somam 339 páginas, todas digitalizadas. A leitura foi amostrada nas primeiras páginas de cada um dos sete PDFs; não é validação integral das 339 páginas nem medição de precisão clínica. O ambiente de desenvolvimento não dispõe de Docker; a imagem deve ser validada no servidor de destino.

## Próximas melhorias recomendadas

- Criar perfis por operadora, com recortes específicos dos campos, para melhorar números e nomes.
- Mostrar miniaturas de todas as páginas e permitir mover entre grupos por arrastar.
- Comparar nomes impressos entre guia e anexos, sinalizando divergências.
- Adicionar usuários individuais e histórico de revisões, caso a empresa precise.
- Só depois avaliar OCR com IA para manuscritos, com decisão explícita sobre infraestrutura local ou serviço externo.

## Desenvolvimento

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
DATA_DIR=/tmp/guias-data APP_USER=admin APP_PASSWORD='uma-senha-longa-aqui' OCR_LANG=eng python app/server.py
```

O pacote não contém os PDFs reais nem dados dos pacientes.
