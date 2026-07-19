"""Primitivas de multiconjunto para matching deterministico."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MultisetGroup[T]:
    key: object
    items: tuple[T, ...]


@dataclass(frozen=True, slots=True)
class ConsumoMulticonjunto[L, R]:
    pares: tuple[tuple[L, R], ...]
    sobras_esquerda: tuple[L, ...]
    sobras_direita: tuple[R, ...]


def agrupar_multiconjunto[T, K](
    items: Iterable[T],
    key: Callable[[T], K],
    order: Callable[[T], Any],
) -> dict[K, tuple[T, ...]]:
    grouped: dict[K, list[T]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {group_key: tuple(sorted(values, key=order)) for group_key, values in grouped.items()}


def consumir_deterministicamente[L, R](
    esquerda: Iterable[L],
    direita: Iterable[R],
    *,
    order_left: Callable[[L], Any],
    order_right: Callable[[R], Any],
) -> ConsumoMulticonjunto[L, R]:
    left = tuple(sorted(esquerda, key=order_left))
    right = tuple(sorted(direita, key=order_right))
    quantidade = min(len(left), len(right))
    return ConsumoMulticonjunto(
        pares=tuple(zip(left[:quantidade], right[:quantidade], strict=True)),
        sobras_esquerda=left[quantidade:],
        sobras_direita=right[quantidade:],
    )
