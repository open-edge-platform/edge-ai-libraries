# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The evaluation harness's own arithmetic, checked on cases with known answers.

The harness itself needs a dataset, real models and tens of minutes, so it does
not run here. What does run is the part that would be worst to get wrong: a
metric with an off-by-one or a mishandled tie reports a number that looks
entirely reasonable and is simply false, and nothing downstream would catch it.
Perfect and worst-case inputs have answers that can be written down.
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "eval_retrieval",
    ),
)

from metrics import rank_of, score, table  # noqa: E402


# --- ranking -------------------------------------------------------------------


def test_the_best_score_is_rank_one_not_rank_zero():
    assert rank_of([0.9, 0.1, 0.2], 0) == 1


def test_a_rank_counts_everything_scoring_higher():
    assert rank_of([0.1, 0.9, 0.5], 0) == 3


def test_a_tie_is_counted_against_the_target():
    """A model that scores everything alike should read as useless, not average.

    Breaking ties in the target's favour would give a constant-output model a
    perfect R@1, which is the most misleading possible answer.
    """
    assert rank_of([0.5, 0.5, 0.5], 0) == 3


# --- the two conventions -------------------------------------------------------


def test_a_perfect_run_scores_one_under_both_conventions():
    result = score([[1], [1], [1]])

    assert result["per_caption"].recall[1] == 1.0
    assert result["per_item"].recall[1] == 1.0
    assert result["per_item"].median_rank == 1.0


def test_the_two_conventions_disagree_when_captions_disagree():
    """One item, two captions: one finds it, one does not.

    Per-caption counts it half found. Per-item counts it found, because any
    caption finding it is the whole criterion. Reporting only one of these is
    how a number becomes incomparable with someone else's.
    """
    result = score([[1, 50]])

    assert result["per_caption"].recall[1] == 0.5
    assert result["per_item"].recall[1] == 1.0


def test_recall_at_five_includes_everything_up_to_five():
    result = score([[1], [5], [6]])

    assert result["per_item"].recall[1] == pytest.approx(1 / 3)
    assert result["per_item"].recall[5] == pytest.approx(2 / 3)
    assert result["per_item"].recall[10] == 1.0


def test_median_rank_of_an_even_count_is_the_midpoint():
    result = score([[1], [2], [3], [10]])

    assert result["per_item"].median_rank == 2.5
    assert result["per_item"].mean_rank == 4.0


def test_an_empty_run_reports_nothing_rather_than_dividing_by_zero():
    result = score([])

    assert result["per_item"].queries == 0
    assert result["per_item"].recall == {}


# --- reporting -----------------------------------------------------------------


def test_the_table_names_every_run_and_convention():
    rendered = table({"exact": score([[1]]), "engine": score([[2]])})

    assert "exact/caption" in rendered
    assert "exact/item" in rendered
    assert "engine/item" in rendered
    assert rendered.count("\n") == 5, "a header, a rule, and four rows"
