"""Grupos de itens similares — fonte única de verdade.

Regra: quando a baixa de um item resultar em saldo negativo e existe item
do mesmo grupo com saldo positivo para o mesmo parceiro/fase, a baixa deve
ser computada no item com saldo disponível.

Atualizado em: 23/08/2026 — ref. planilha ITENS SIMILARES.xlsx
"""

SIMILAR_GROUPS: list[list[str]] = [
    # APs Intelbras Wi-Fi 6 (teto/indoor)
    [
        'INTELBRAS AP 3620',
        'INTELBRAS AP RW6181',
        'INTELBRAS AP RW6302',
        'INTELBRAS AP RW6305W',
        'INTELBRAS AP RW3620AP',
    ],
    # APs TP-Link (EAP série 610/613/650)
    [
        'TP-LINK EAP 610',
        'TP-LINK EAP613',
        'TP-LINK EAP 613',
        'TP-LINK EAP650',
        'TP-LINK EAP 650',
    ],
    # Switches TP-Link PoE
    [
        'SWITCH TP-LINK SG2016P',
        'SWITCH TP-LINK ES210GMP',
        'SWITCH TP-LINK SG2210MP',
    ],
    # Racks 5U e 8U
    [
        'RACK 5U',
        'RACK 8U',
    ],
    # Roteadores Intelbras R3005/R3006
    [
        'INTELBRAS 3.005',
        'INTELBRAS R3006MG',
    ],
    # Roteadores Intelbras R3006G-P / R3010G-P
    [
        'INTELBRAS R3006G-P',
        'INTELBRAS R3010G-P',
    ],
]

# Lookup rápido: nome_upper → lista de similares (upper, sem o próprio item)
_ITEM_TO_SIMILARES: dict[str, list[str]] = {}
for _grp in SIMILAR_GROUPS:
    _grp_upper = [n.upper() for n in _grp]
    for _nome in _grp_upper:
        _ITEM_TO_SIMILARES[_nome] = [s for s in _grp_upper if s != _nome]


def similares(nome_item: str) -> list[str]:
    """Retorna lista de nomes similares (upper) para o item dado, ou [] se não houver grupo."""
    return _ITEM_TO_SIMILARES.get(nome_item.strip().upper(), [])


def mesmo_grupo(nome_a: str, nome_b: str) -> bool:
    """True se os dois itens pertencem ao mesmo grupo de similaridade."""
    ua, ub = nome_a.strip().upper(), nome_b.strip().upper()
    return ub in _ITEM_TO_SIMILARES.get(ua, [])
