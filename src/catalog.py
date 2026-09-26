"""读取问题分类与角色契约，作为核验服务的输入。"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceKind:
    """一类需要留存的证据，如告知文本、注销路径。"""

    code: str
    name: str


@dataclass(frozen=True)
class ProblemCategory:
    """一类监管问题及其闭环所需的证据种类。"""

    code: str
    name: str
    evidence_kinds: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    """问题分类目录：证据种类全集 + 各问题分类所需的证据子集。"""

    version: int
    evidence_kinds: tuple[EvidenceKind, ...]
    categories: tuple[ProblemCategory, ...]

    def category(self, code: str) -> ProblemCategory:
        for category in self.categories:
            if category.code == code:
                return category
        raise KeyError(f"未知问题分类: {code}")

    def has_evidence_kind(self, code: str) -> bool:
        return any(kind.code == code for kind in self.evidence_kinds)


@dataclass(frozen=True)
class Role:
    """一个需要独立签署结论的角色。"""

    code: str
    name: str
    conclusion_scope: str


@dataclass(frozen=True)
class RoleContract:
    """角色契约：哪些角色必须各自签署结论。"""

    version: int
    roles: tuple[Role, ...]

    def role(self, code: str) -> Role:
        for role in self.roles:
            if role.code == code:
                return role
        raise KeyError(f"未知角色: {code}")

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(role.code for role in self.roles)


def load_catalog(path: Path) -> Catalog:
    """读取问题分类目录，并校验分类引用的证据种类均已声明。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not {"version", "evidence_kinds", "categories"}.issubset(data):
        raise ValueError("问题分类资料缺少必要字段")
    kinds = tuple(
        EvidenceKind(code=item["code"], name=item["name"])
        for item in data["evidence_kinds"]
    )
    known = {kind.code for kind in kinds}
    categories = []
    for item in data["categories"]:
        required = tuple(item["evidence_kinds"])
        unknown = [code for code in required if code not in known]
        if unknown:
            raise ValueError(f"分类 {item['code']} 引用了未声明的证据种类: {unknown}")
        categories.append(
            ProblemCategory(
                code=item["code"], name=item["name"], evidence_kinds=required
            )
        )
    if not categories:
        raise ValueError("问题分类不能为空")
    return Catalog(
        version=data["version"], evidence_kinds=kinds, categories=tuple(categories)
    )


def load_roles(path: Path) -> RoleContract:
    """读取角色契约。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not {"version", "roles"}.issubset(data):
        raise ValueError("角色契约缺少必要字段")
    roles = tuple(
        Role(
            code=item["code"],
            name=item["name"],
            conclusion_scope=item["conclusion_scope"],
        )
        for item in data["roles"]
    )
    if not roles:
        raise ValueError("角色契约不能为空")
    return RoleContract(version=data["version"], roles=roles)
