"""Construcao e serializacao de chaves de matching."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from conciliacao.domain.enums import Modalidade, Operadora


@dataclass(frozen=True, slots=True, order=True)
class MatchingKey:
    operadora: Operadora
    modalidade: Modalidade
    data: date
    valor: Decimal
    bandeira: str | None = None

    def sem_bandeira(self) -> "MatchingKey":
        return MatchingKey(
            operadora=self.operadora,
            modalidade=self.modalidade,
            data=self.data,
            valor=self.valor,
            bandeira=None,
        )

    def sem_valor(self) -> tuple[Operadora, Modalidade, date, str | None]:
        return (self.operadora, self.modalidade, self.data, self.bandeira)

    def serialize(self) -> str:
        parts = [
            self.operadora.value,
            self.modalidade.value,
            self.data.isoformat(),
            f"{self.valor:.2f}",
        ]
        if self.bandeira:
            parts.append(self.bandeira)
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class BaseMatchingKey:
    operadora: Operadora
    modalidade: Modalidade
    data: date
    valor: Decimal

    def serialize(self) -> str:
        return "|".join(
            [
                self.operadora.value,
                self.modalidade.value,
                self.data.isoformat(),
                f"{self.valor:.2f}",
            ]
        )
