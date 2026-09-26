"""问题分类与角色契约:核验服务的两类输入。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProblemCategory:
    """通报中的一类个人信息收集使用问题。"""

    code: str
    title: str


@dataclass(frozen=True)
class RoleContract:
    """一个签署角色及其结论覆盖的证据类别。"""

    role: str
    title: str
    covers: tuple[str, ...]


def load_problem_catalog(path: Path) -> tuple[ProblemCategory, ...]:
    """读取问题分类,编码不得重复。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("categories")
    if not entries:
        raise ValueError("问题分类缺少 categories 字段")
    catalog = tuple(ProblemCategory(code=entry["code"], title=entry["title"]) for entry in entries)
    codes = [category.code for category in catalog]
    if len(set(codes)) != len(codes):
        raise ValueError("问题分类存在重复编码")
    return catalog


def load_role_contract(path: Path) -> tuple[RoleContract, ...]:
    """读取角色契约,角色不得重复。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("roles")
    if not entries:
        raise ValueError("角色契约缺少 roles 字段")
    roles = tuple(
        RoleContract(
            role=entry["role"],
            title=entry["title"],
            covers=tuple(entry["covers"]),
        )
        for entry in entries
    )
    names = [contract.role for contract in roles]
    if len(set(names)) != len(names):
        raise ValueError("角色契约存在重复角色")
    return roles
