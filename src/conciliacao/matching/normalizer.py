"""Normalizacao conservadora para matching."""

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.domain.models import RegistroSistema, TransacaoOperadora
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.utils.text import normalize_text


def categoria_da_transacao(transacao: TransacaoOperadora) -> CategoriaFiltroVelo | None:
    if transacao.modalidade is None:
        return None
    return categoria_por_operadora_modalidade(transacao.operadora, transacao.modalidade)


def categoria_do_registro(registro: RegistroSistema) -> CategoriaFiltroVelo | None:
    if registro.categoria_origem is not None:
        try:
            return CategoriaFiltroVelo(registro.categoria_origem)
        except ValueError:
            return None
    operadora = normalizar_operadora(registro.operadora)
    modalidade = normalizar_modalidade_sistema(registro.forma_recebimento)
    if operadora is None or modalidade is None:
        return None
    return categoria_por_operadora_modalidade(operadora, modalidade)


def categoria_por_operadora_modalidade(
    operadora: Operadora, modalidade: Modalidade
) -> CategoriaFiltroVelo:
    match (operadora, modalidade):
        case (Operadora.CIELO, Modalidade.CREDITO):
            return CategoriaFiltroVelo.CIELO_CREDITO
        case (Operadora.CIELO, Modalidade.DEBITO):
            return CategoriaFiltroVelo.CIELO_DEBITO
        case (Operadora.CIELO, Modalidade.PIX):
            return CategoriaFiltroVelo.CIELO_PIX
        case (Operadora.QUICKPAY, Modalidade.CREDITO):
            return CategoriaFiltroVelo.QUICKPAY_CREDITO
        case (Operadora.QUICKPAY, Modalidade.DEBITO):
            return CategoriaFiltroVelo.QUICKPAY_DEBITO
        case (Operadora.QUICKPAY, Modalidade.PIX):
            return CategoriaFiltroVelo.QUICKPAY_PIX
    raise ValueError("categoria Velo desconhecida")


def normalizar_operadora(value: object | None) -> Operadora | None:
    if isinstance(value, Operadora):
        return value
    if value is None:
        return None
    comparable = normalize_text(str(value)).comparavel
    if "cielo" in comparable:
        return Operadora.CIELO
    if "quickpay" in comparable or "quick pay" in comparable:
        return Operadora.QUICKPAY
    return None


def normalizar_modalidade_sistema(value: object | None) -> Modalidade | None:
    if value is None:
        return None
    comparable = normalize_text(str(value)).comparavel
    if "pix" in comparable:
        return Modalidade.PIX
    if "credito" in comparable:
        return Modalidade.CREDITO
    if "debito" in comparable or "dedido" in comparable:
        return Modalidade.DEBITO
    return None


def normalizar_bandeira_operadora(transacao: TransacaoOperadora) -> str | None:
    return normalizar_bandeira_texto(transacao.bandeira)


def normalizar_bandeira_sistema(registro: RegistroSistema) -> str | None:
    tipo_cartao = normalizar_bandeira_texto(registro.tipo_cartao)
    if tipo_cartao is not None:
        return tipo_cartao
    forma = normalizar_bandeira_texto(registro.forma_recebimento)
    return forma


def normalizar_bandeira_texto(value: object | None) -> str | None:
    if value is None:
        return None
    comparable = normalize_text(str(value)).comparavel
    if "master" in comparable:
        return "mastercard"
    if "visa" in comparable:
        return "visa"
    if "pix" in comparable:
        return "pix"
    return None
