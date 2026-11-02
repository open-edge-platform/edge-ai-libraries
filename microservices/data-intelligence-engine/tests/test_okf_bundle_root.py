# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""OKF links meet the concepts they name, however the bundle was uploaded."""

import pytest

pytest.importorskip("yaml")

from core.knowledge.okf import parse_okf_bundle


def _bundle(root):
    (root / "act").mkdir(parents=True)
    (root / "defendant").mkdir()
    (root / "index.md").write_text("# OKF Bundle Index\n", encoding="utf-8")
    (root / "act" / "act-01.md").write_text(
        "---\ntype: Act\ntitle: ACT-01\n---\nCommitted by [Zhou](../defendant/周文斌.md) — committed_by\n",
        encoding="utf-8",
    )
    (root / "defendant" / "周文斌.md").write_text("---\ntype: Defendant\ntitle: 周文斌\n---\nDefendant.\n", encoding="utf-8")


def _links(nodes):
    return {node.cid: node.links for node in nodes}


@pytest.mark.parametrize("wrapped", [False, True])
def test_link_targets_are_concept_ids_even_inside_a_wrapper_folder(tmp_path, wrapped):
    upload = tmp_path / "dossier"
    _bundle(upload / "okf_bundle_v2" if wrapped else upload)

    nodes = parse_okf_bundle(upload)
    cids = {node.cid for node in nodes}

    assert cids == {"act/act-01", "defendant/周文斌"}
    targets = {target for links in _links(nodes).values() for target, _ in links}
    assert targets == {"defendant/周文斌"} and targets <= cids
    assert {node.okf_file_path for node in nodes} == {"/act/act-01.md", "/defendant/周文斌.md"}


def test_generated_type_directory_names_resolve_to_canonical_concept_ids(tmp_path):
    (tmp_path / "person").mkdir()
    (tmp_path / "care-plan").mkdir()
    (tmp_path / "index.md").write_text("# index\n", encoding="utf-8")
    (tmp_path / "person/ada.md").write_text(
        "---\ntype: Person\ntitle: Ada\n---\n[Plan](../care-plan/recovery.md) — owns\n",
        encoding="utf-8",
    )
    (tmp_path / "care-plan/recovery.md").write_text(
        "---\ntype: Care Plan\ntitle: Recovery\n---\n[Ada](../person/ada.md) — owned_by\n",
        encoding="utf-8",
    )

    nodes = {node.title: node for node in parse_okf_bundle(tmp_path)}
    assert nodes["Ada"].links == [(nodes["Recovery"].cid, "owns")]
    assert nodes["Recovery"].links == [("people/ada", "owned_by")]
