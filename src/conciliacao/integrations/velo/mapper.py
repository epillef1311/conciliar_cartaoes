"""Mapeamento da resposta Velo para modelos de dominio."""

from conciliacao.domain.models import RegistroSistema
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.schemas import RegistroConciliacaoApi


def map_registro_sistema(
    registro: RegistroConciliacaoApi,
    *,
    categoria: CategoriaFiltroVelo,
) -> RegistroSistema:
    return RegistroSistema.model_validate(
        {
            "contaPacotePagamentoUnicoId": str(registro.conta_pacote_pagamento_unico_id),
            "operadora": registro.operadora,
            "operadoraId": registro.operadora_id,
            "formaRecebimento": registro.forma_recebimento,
            "formaRecebimentoId": registro.forma_recebimento_id,
            "tipo_cartao": registro.tipo_cartao,
            "valor": registro.valor,
            "valorTaxaCartao": registro.valor_taxa_cartao,
            "dataCadastro": registro.data_cadastro,
            "dataVencimento": registro.data_vencimento,
            "cadastroCaixaId": (
                str(registro.cadastro_caixa_id)
                if registro.cadastro_caixa_id is not None
                else None
            ),
            "categoria_origem": categoria.value,
            "dados_originais": registro.raw_payload(),
            "identificadores_api": {
                "operadoraId": registro.operadora_id,
                "formaRecebimentoId": registro.forma_recebimento_id,
                "contaPacotePagamentoUnicoId": str(registro.conta_pacote_pagamento_unico_id),
            },
        }
    )
