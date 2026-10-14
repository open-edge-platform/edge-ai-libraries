# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from .config import config
from .logger import logger
from bert_score import BERTScorer
from bs4 import BeautifulSoup
from nltk.tokenize import sent_tokenize
from rouge_score import rouge_scorer
from sentence_transformers import SentenceTransformer, util
from scipy.stats import kendalltau
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, Any
import csv
import markdown
import numpy as np
import os
import nltk
import torch


class Evaluator:
    def __init__(
        self,
        bert_scorer_model_name: str = None,
        sbert_model_name: str = None,
        nli_model_name: str = None,
        nli_model_revision: str = None
    ):
        """
        Initialize the evaluator class.

        Args:
            bert_scorer_model_name: BERT scorer model name
            sbert_model_name: Sentence transformer model name
            nli_model_name: Natural Language Inference model name
            nli_model_revision: Pinned commit/revision for the NLI model
        """

        # Download necessary NLTK resources
        nltk.download('punkt')
        nltk.download('punkt_tab')

        # Initialize bert-scorer model
        self.bert_scorer = BERTScorer(model_type=bert_scorer_model_name)

        # Initialize the Sentence Transformer model
        self.sentence_model = SentenceTransformer(
            sbert_model_name,
            cache_folder=f"{config._CACHE_DIR}/{sbert_model_name}"
        )

        # Initialize the NLI model and tokenizer
        self.nli_tokenizer = AutoTokenizer.from_pretrained(
            nli_model_name,
            revision=nli_model_revision,
            cache_dir=f"{config._CACHE_DIR}/{nli_model_name}"
        )

        self.nli_model = AutoModelForSequenceClassification.from_pretrained(
            nli_model_name,
            revision=nli_model_revision,
            cache_dir=f"{config._CACHE_DIR}/{nli_model_name}"
        )


    def _calculate_semantic_score(self, generated: str="", reference: str="") -> Dict[str, Any]:
        """
        Calculate semantic similarity score between generated and reference text using Sentence-BERT embeddings.

        Args:
            generated (str): The generated text to be evaluated.
            reference (str): The reference text to compare against.

        Returns:
            dict: A dictionary containing precision, recall, F1 score, and similarity score.
        """

        logger.info(f"Calculating semantic score...")
        if not generated or not reference:
            raise ValueError("Both 'generated' and 'reference' must be non-empty strings.")

        # Tensor output
        embeddings = self.sentence_model.encode([generated, reference], convert_to_tensor=True)

        similarity = float(util.cos_sim(embeddings[0], embeddings[1]).item())

        return {
            "reference": reference,
            "generated": generated,
            "semantic_similarity_score": round(similarity, 4)
        }


    def _calculate_bert_score(self, generated: str = "", reference: str = "") -> Dict[str, Any]:
        """
        Calculate BERTScore between generated and reference text.

        Args:
            generated (str): The generated text to be evaluated.
            reference (str): The reference text to compare against.

        Returns:
            dict: A dictionary containing precision, recall, and F1 score.
        """
        logger.info("Calculating BERT score...")
        P, R, F1 = self.bert_scorer.score([generated], [reference])
        return {
            "reference": reference,
            "generated": generated,
            "precision": round(float(P[0].item()), 4),
            "recall": round(float(R[0].item()), 4),
            "f1_score": round(float(F1[0].item()), 4)
        }


    def _calculate_rouge_score(self, generated: str = "", reference: str = "") -> list[Dict[str, Any]]:
        """
        Calculate ROUGE-1, ROUGE-2 and ROUGE-L scores between generated and reference text.

        Args:
            generated (str): The generated text to be evaluated.
            reference (str): The reference text to compare against.

        Returns:
            dict: A dictionary containing precision, recall, and F1 scores for ROUGE-1, ROUGE-2, and ROUGE-L.
        """
        logger.info("Calculating ROUGE score...")
        scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
        scores = scorer.score(reference, generated)  # reference first, then generated

        return {
            "reference": reference,
            "generated": generated,
            "rouge1": {
                "precision": round(scores["rouge1"].precision, 4),
                "recall": round(scores["rouge1"].recall, 4),
                "f1_score": round(scores["rouge1"].fmeasure, 4)
            },
            "rouge2": {
                "precision": round(scores["rouge2"].precision, 4),
                "recall": round(scores["rouge2"].recall, 4),
                "f1_score": round(scores["rouge2"].fmeasure, 4)
            },
            "rougeL": {
                "precision": round(scores["rougeL"].precision, 4),
                "recall": round(scores["rougeL"].recall, 4),
                "f1_score": round(scores["rougeL"].fmeasure, 4)
            }
        }


    def _calculate_average_scores(self, pairs: list[tuple[str, str]]) -> list[Dict[str, Any]]:
        """
        Calculate average ROUGE and Semantic scores for multiple (generated, reference) pairs.

        Args:
            pairs (list of tuples): List of (generated, reference) text pairs.

        Returns:
            dict: Dictionary containing average precision, recall, and F1 scores for ROUGE-1, ROUGE-2, ROUGE-L, and Semantic metrics.
        """
        logger.info("Calculating average scores for multiple pairs...")
        # Holders for metrics
        rouge1_p, rouge1_r, rouge1_f = [], [], []
        rouge2_p, rouge2_r, rouge2_f = [], [], []
        rougel_p, rougel_r, rougel_f = [], [], []
        semantic_s = []

        for generated, reference in pairs:
            rouge_scores = self._calculate_rouge_score(generated, reference)
            semantic_scores = self._calculate_semantic_score(generated, reference)

            rouge1_p.append(rouge_scores["rouge1"]["precision"])
            rouge1_r.append(rouge_scores["rouge1"]["recall"])
            rouge1_f.append(rouge_scores["rouge1"]["f1_score"])

            rouge2_p.append(rouge_scores["rouge2"]["precision"])
            rouge2_r.append(rouge_scores["rouge2"]["recall"])
            rouge2_f.append(rouge_scores["rouge2"]["f1_score"])

            rougel_p.append(rouge_scores["rougeL"]["precision"])
            rougel_r.append(rouge_scores["rougeL"]["recall"])
            rougel_f.append(rouge_scores["rougeL"]["f1_score"])

            semantic_s.append(semantic_scores["semantic_similarity_score"])

        # return average dictionary
        return {
            "rouge1": {
                "precision": round(np.mean(rouge1_p), 4),
                "recall": round(np.mean(rouge1_r), 4),
                "f1_score": round(np.mean(rouge1_f), 4),
            },
            "rouge2": {
                "precision": round(np.mean(rouge2_p), 4),
                "recall": round(np.mean(rouge2_r), 4),
                "f1_score": round(np.mean(rouge2_f), 4),
            },
            "rougeL": {
                "precision": round(np.mean(rougel_p), 4),
                "recall": round(np.mean(rougel_r), 4),
                "f1_score": round(np.mean(rougel_f), 4),
            },
            "semantic": {
                "semantic_similarity_score": round(np.mean(semantic_s), 4),
            }
        }


    def _calculate_kendall_tau_norm(self, order_indices: list = []) -> float:
        """
        Calculate normalized Kendall's tau correlation coefficient.

        Args:
            order_indices (list): List of indices representing order

        Returns:
            float or None: Normalized Kendall's tau value (0-1 range) or None if invalid
        """
        positions = list(range(len(order_indices)))
        tau, _ = kendalltau(positions, order_indices)

        kendall_tau_norm = None
        if tau is not None and not (isinstance(tau, float) and (tau != tau)):  # not NaN
            kendall_tau_norm = (tau + 1.0) / 2.0  # map from [-1,1] to [0,1]

        return round(kendall_tau_norm, 3) if kendall_tau_norm is not None else None


    def _calculate_nli_entailment_score(self, premise: str = "", hypothesis: str = "") -> Dict[str, float]:
        """
        Calculate the NLI probability scores for Entailment, Neutral, and Contradiction.

        Args:
            premise (str): The premise text.
            hypothesis (str): The hypothesis text.

        Returns:
            dict: Dictionary with 'entailment', 'neutral', and 'contradiction' probabilities.
        """
        inputs = self.nli_tokenizer(premise, hypothesis, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self.nli_model(**inputs).logits
        probs = torch.softmax(logits, dim=1)[0]

        # Find indices for each label
        entailment_idx = next(
            (idx for idx, lbl in self.nli_model.config.id2label.items() if lbl.lower() == "entailment"),
            None
        )
        neutral_idx = next(
            (idx for idx, lbl in self.nli_model.config.id2label.items() if lbl.lower() == "neutral"),
            None
        )
        contradiction_idx = next(
            (idx for idx, lbl in self.nli_model.config.id2label.items() if lbl.lower() == "contradiction"),
            None
        )

        return {
            "entailment": round(float(probs[entailment_idx].item()), 4) if entailment_idx is not None else 0.0,
            "neutral": round(float(probs[neutral_idx].item()), 4) if neutral_idx is not None else 0.0,
            "contradiction": round(float(probs[contradiction_idx].item()), 4) if contradiction_idx is not None else 0.0
        }


    def _evaluate_factual_consistency(self, generated: str="", reference: str="") -> str:
        """
        Evaluates the factual consistency between a generated sentence and a reference sentence using a Natural Language Inference (NLI) model.
        The function applies the NLI model to determine the relationship (entailment, neutral, contradiction) between the two sentences.

        Args:
            generated (str): The generated sentence to be evaluated.
            reference (str): The reference sentence to compare against.

        Returns:
            dict: A dictionary containing the reference sentence, generated sentence, and the factual consistency label.
        """
        logger.info("Calculating factual consistency...")

        # Apply NLI model to best match sentence to find relationship
        # Convert text sentences into numerical tokens that model can understand
        inputs = self.nli_tokenizer(reference, generated, return_tensors="pt", truncation=True)
        # NLI models itself usually built using pyTorch, so we use torch.no_grad() to avoid computing gradients (saves memory)
        # Telling PyTorch: "we are in inference mode, not training mode"
        with torch.no_grad():
            # Passes the tokenized inputs through the NLI model to get raw prediction scores(logits) for each possible class
            logits = self.nli_model(**inputs).logits
            # Find which class has highest score
            predicted_class = logits.argmax(dim=1).item()
            # Map the predicted class index to human-readable label
            label = self.nli_model.config.id2label[predicted_class]

        return {
            "reference": reference,
            "generated": generated,
            "factual_consistency": label
        }


    def _evaluate_temporal_coherence_score(self, order_indices: list = []) -> dict:
        """Evaluates the temporal coherence of a generated summary based on the order of matched sentences compared to a reference summary.
        The function calculates two metrics:
        1. Temporal Coherence Score: Measures the proportion of sentences that are in the correct order based on the indices of matched sentences.
        2. Pairwise Order Accuracy: Evaluates the accuracy of the order of sentences by comparing all pairs of sentences and counting how many are in the correct order.
        The results include the order indices, temporal coherence score, pairwise order accuracy, and counts of temporal violations and out-of-order pairs.
        Args:
            order_indices (list): A list of indices representing the order of matched sentences in the generated summary compared to the reference summary.
        Returns:
            dict: A dictionary containing the order indices, temporal coherence score, pairwise order accuracy, and counts of temporal violations and out-of-order pairs.
        """
        logger.info("Evaluating temporal coherence...")
        n = len(order_indices)

        if n <= 1:
            return {
                'order_indices': order_indices,
                'temporal_score': 1.0,
                'pairwise_order_accuracy': 1.0,
                'temporal_violations': 0,
                'out_of_order_pairs': 0,
                'total_pairs': 0
            }

        # Calculate both metrics in combined loops
        temporal_violations = 0
        out_of_order = 0
        total_pairs = 0

        # Backward jump check
        for i in range(1, n):
            if order_indices[i] < order_indices[i - 1]:
                temporal_violations += 1

        # Pairwise accuracy
        for i in range(n):
            for j in range(i + 1, n):
                total_pairs += 1
                if order_indices[j] < order_indices[i]:
                    out_of_order += 1

        temporal_score = round(1 - temporal_violations / (n - 1), 3)
        pairwise_order_accuracy = round(1 - out_of_order / total_pairs, 3)

        # Calculate kendall's tau correlation coefficient
        kendall_tau_norm = self._calculate_kendall_tau_norm(order_indices)

        return {
            'order_indices': order_indices,
            'temporal_score': temporal_score,
            'pairwise_order_accuracy': pairwise_order_accuracy,
            'temporal_violations': temporal_violations,
            'out_of_order_pairs': out_of_order,
            'total_pairs': total_pairs,
            'kendall_tau_norm': kendall_tau_norm
        }


    def _compute_factual_stats(self, source: str = "", target: str = "") -> dict:
        """
        Compute factual consistency statistics by matching each source sentence
        to its best match in target sentences.

        Args:
            source (str): Source text whose sentences are iterated.
            target (str): Target text to match against.

        Returns:
            dict: Counts and ratios for entailment, neutral, contradiction and cosine scores.
        """
        entailment_count = 0
        contradiction_count = 0
        neutral_count = 0
        total_cosine_score = 0.0

        src_sentences = sent_tokenize(source)
        tgt_sentences = sent_tokenize(target)
        tgt_embeddings = self.sentence_model.encode(tgt_sentences, convert_to_tensor=True)

        for src_sentence in src_sentences:
            src_embedding = self.sentence_model.encode(src_sentence, convert_to_tensor=True)
            cosine_scores = util.cos_sim(src_embedding, tgt_embeddings)[0]
            best_match_idx = torch.argmax(cosine_scores).item()
            best_match_sentence = tgt_sentences[best_match_idx]

            factual_result = self._evaluate_factual_consistency(best_match_sentence, src_sentence)
            label = factual_result["factual_consistency"]

            if label == "entailment":
                entailment_count += 1
            elif label == "neutral":
                neutral_count += 1
            else:
                contradiction_count += 1

            total_cosine_score += float(cosine_scores[best_match_idx].item())

        total = entailment_count + neutral_count + contradiction_count
        return {
            "total": total,
            "entailment": entailment_count,
            "neutral": neutral_count,
            "contradiction": contradiction_count,
            "total_cosine_score": round(total_cosine_score, 4),
            "entailment_ratio": round(entailment_count / total, 4) if total > 0 else 0,
            "neutral_ratio": round(neutral_count / total, 4) if total > 0 else 0,
            "contradiction_ratio": round(contradiction_count / total, 4) if total > 0 else 0,
            "average_cosine_score": round(total_cosine_score / total, 4) if total > 0 else 0,
        }


    def _compute_menli_score(self, generated: str = "", reference: str = "") -> Dict[str, float]:
        """
        Compute MENLI score using E - N - 2C formula with bidirectional sentence-level scoring.

        M1 (S→G / Precision): For each sentence in generated, find best match in reference,
                              calculate E - N - 2C, then average across all sentences.
        M2 (G→S / Recall): For each sentence in reference, find best match in generated,
                           calculate E - N - 2C, then average across all sentences.
        MENLI = (M1 + M2) / 2

        Args:
            generated (str): The generated summary text.
            reference (str): The reference summary text.

        Returns:
            dict: Dictionary containing m1, m2, and menli_score values.
        """
        gen_sentences = sent_tokenize(generated)
        ref_sentences = sent_tokenize(reference)

        # M1: Generated → Reference (Precision)
        m1_scores = []
        if len(gen_sentences) > 0 and len(ref_sentences) > 0:
            ref_embeddings = self.sentence_model.encode(ref_sentences, convert_to_tensor=True)

            for gen_sentence in gen_sentences:
                gen_embedding = self.sentence_model.encode(gen_sentence, convert_to_tensor=True)
                cosine_scores = util.cos_sim(gen_embedding, ref_embeddings)[0]
                best_match_idx = torch.argmax(cosine_scores).item()
                best_match_sentence = ref_sentences[best_match_idx]

                # Get E, N, C probabilities (generated as hypothesis, reference as premise)
                probs = self._calculate_nli_entailment_score(premise=best_match_sentence, hypothesis=gen_sentence)
                # Calculate E - N - 2C
                score = probs["entailment"] - probs["neutral"] - 2 * probs["contradiction"]
                m1_scores.append(score)

        # M2: Reference → Generated (Recall)
        m2_scores = []
        if len(ref_sentences) > 0 and len(gen_sentences) > 0:
            gen_embeddings = self.sentence_model.encode(gen_sentences, convert_to_tensor=True)

            for ref_sentence in ref_sentences:
                ref_embedding = self.sentence_model.encode(ref_sentence, convert_to_tensor=True)
                cosine_scores = util.cos_sim(ref_embedding, gen_embeddings)[0]
                best_match_idx = torch.argmax(cosine_scores).item()
                best_match_sentence = gen_sentences[best_match_idx]

                # Get E, N, C probabilities (reference as premise, generated as hypothesis)
                probs = self._calculate_nli_entailment_score(premise=ref_sentence, hypothesis=best_match_sentence)
                # Calculate E - N - 2C
                score = probs["entailment"] - probs["neutral"] - 2 * probs["contradiction"]
                m2_scores.append(score)

        # Calculate averages
        m1 = sum(m1_scores) / len(m1_scores) if len(m1_scores) > 0 else 0.0
        m2 = sum(m2_scores) / len(m2_scores) if len(m2_scores) > 0 else 0.0

        # Final MENLI score
        menli_score = (m1 + m2) / 2
        return {
            "m1": round(m1, 4),
            "m2": round(m2, 4),
            "menli_score": round(menli_score, 4),
        }


    def _evaluate_summaries(self, reference: str="", generated: str="") -> list[Dict[str, Any]]:
        """
        Evaluates the factual consistency between a reference summary and a generated summary using sentence similarity and Natural Language Inference (NLI).
        The function compares each sentence in the reference summary to its most similar sentence in the generated summary using sentence embeddings and cosine similarity.
        It then applies an NLI model to determine the relationship (entailment, neutral, contradiction) between the matched sentences.
        The results include per-sentence comparison details and an aggregated summary of factual consistency statistics.

        Args:
            reference (str): The reference summary text to compare against.
            generated (str): The generated summary text to be evaluated.

        Returns:
            List[dict]: A list of dictionaries containing:
            - Per-sentence comparison details:
                "reference_sentence": str,
                "matched_sentence": str,
                "similarity_score": float,
                "factual_consistency": str
            - A summary dictionary with factual consistency statistics:
                    "total_sentences_compared": int,
                    "entailment": int,
                    "neutral": int,
                    "contradiction": int,
                    "entailment_ratio": float,
                    "neutral_ratio": float,
                    "contradiction_ratio": float
        """

        # Order indices
        order_indices = []

        # Split the texts into sentences
        ref_sentences = sent_tokenize(reference)
        gen_sentences = sent_tokenize(generated)

        # Encode sentences from generated summary
        gen_embeddings = self.sentence_model.encode(gen_sentences, convert_to_tensor=True)

        # Compare each sentence in reference summary to best match in generated summary
        results = []
        for ref_sentence in ref_sentences:
            ref_embedding = self.sentence_model.encode(ref_sentence, convert_to_tensor=True)
            cosine_scores = util.cos_sim(ref_embedding, gen_embeddings)[0]
            best_match_idx = torch.argmax(cosine_scores).item()
            order_indices.append(best_match_idx)
            best_match_sentence = gen_sentences[best_match_idx]

            # Evaluate factual consistency using NLI model
            factual_consistency_result = self._evaluate_factual_consistency(best_match_sentence, ref_sentence)
            factual_consistency_label = factual_consistency_result["factual_consistency"]

            # Evaluate bert score
            bert_result = self._calculate_bert_score(best_match_sentence, ref_sentence)
            bert_score_f1 = bert_result["f1_score"]
            bert_score_precision = bert_result["precision"]
            bert_score_recall = bert_result["recall"]

            # Evaluate rouge score
            rouge_result = self._calculate_rouge_score(best_match_sentence, ref_sentence)
            rouge1_score = rouge_result["rouge1"]
            rouge2_score = rouge_result["rouge2"]
            rougel_score = rouge_result["rougeL"]

            results.append(
                {
                    "reference_sentence": ref_sentence,
                    "matched_sentence":best_match_sentence,
                    "similarity_score": round(float(cosine_scores[best_match_idx].item()), 4),
                    "factual_consistency": factual_consistency_label,
                    "bert_score": {
                        "f1_score": bert_score_f1,
                        "precision": bert_score_precision,
                        "recall": bert_score_recall
                    },
                    "rouge_score": {
                        "rouge1": rouge1_score,
                        "rouge2": rouge2_score,
                        "rougeL": rougel_score
                    }
                }
            )

        temporal_coherence_score = self._evaluate_temporal_coherence_score(order_indices)

        # Derive r→g stats directly from the per-sentence results already computed above
        labels_rg = [r["factual_consistency"] for r in results]
        total_rg = len(labels_rg)
        entailment_rg = labels_rg.count("entailment")
        neutral_rg = labels_rg.count("neutral")
        contradiction_rg = total_rg - entailment_rg - neutral_rg
        total_cosine_rg = round(sum(r["similarity_score"] for r in results), 4)
        stats_rg = {
            "total": total_rg,
            "entailment": entailment_rg,
            "neutral": neutral_rg,
            "contradiction": contradiction_rg,
            "total_cosine_score": total_cosine_rg,
            "entailment_ratio": round(entailment_rg / total_rg, 4) if total_rg > 0 else 0,
            "neutral_ratio": round(neutral_rg / total_rg, 4) if total_rg > 0 else 0,
            "contradiction_ratio": round(contradiction_rg / total_rg, 4) if total_rg > 0 else 0,
            "average_cosine_score": round(total_cosine_rg / total_rg, 4) if total_rg > 0 else 0,
        }
        stats_gr = self._compute_factual_stats(generated, reference)

        # Calculate MENLI score using E - N - 2C formula with bidirectional sentence-level scoring
        # M1 (S→G / precision): for each generated sentence, find best match in reference
        # M2 (G→S / recall): for each reference sentence, find best match in generated
        # MENLI = (M1 + M2) / 2
        menli_result = self._compute_menli_score(generated, reference)

        results.append({
            "Temporal Coherence Summary": temporal_coherence_score
        })

        results.append({
            "Factual Consistency Summary": [
                {"Metric": "total_sentences_compared",   "Value": stats_rg["total"]},
                {"Metric": "total_cosine_score",         "Value": f"{stats_rg['total_cosine_score']}/{stats_rg['total']}"},
                {"Metric": "entailment",                 "Value": stats_rg["entailment"]},
                {"Metric": "neutral",                    "Value": stats_rg["neutral"]},
                {"Metric": "contradiction",              "Value": stats_rg["contradiction"]},
                {"Metric": "entailment_ratio",           "Value": stats_rg["entailment_ratio"]},
                {"Metric": "neutral_ratio",              "Value": stats_rg["neutral_ratio"]},
                {"Metric": "contradiction_ratio",        "Value": stats_rg["contradiction_ratio"]},
                {"Metric": "average_cosine_score",       "Value": f"{stats_rg['average_cosine_score']}/1.0"},
                {"Metric": "Reference → Generated",         "Value": menli_result["m1"]},
                {"Metric": "Generated → Reference",         "Value": menli_result["m2"]},
                {"Metric": "MENLI_Score",                "Value": menli_result["menli_score"]},
            ]
        })

        return results



    def run_evaluation_from_file(self, file_path:str) -> list[Dict[str, Any]]:
        """
        Runs evaluation based on the file type (.tsv or .md) and returns the results.

        Args:
            file_path (str): Path to the input file (.tsv or .md).

        Returns:
            list of dict: Evaluation results containing metrics scores and other relevant information.
        """
        logger.info(f"Running evaluation from file: {file_path}")
        results = {
            "file": os.path.basename(file_path),
            "metrics_scores": []
        }
        with open(file_path, newline="", encoding="utf-8") as file:
            if file_path.lower().endswith(".tsv"):
                reader = csv.DictReader(file, delimiter="\t")
                for row in reader:
                    generated = row["Generated"]
                    reference = row["Reference"]
                    scores = self._calculate_average_scores([(generated, reference)])
                    results["metrics_scores"].append(scores)

                return results

            elif file_path.lower().endswith(".md"):
                md_text = file.read()

                # Convert markdown to HTML
                html = markdown.markdown(md_text)

                # Parse HTML with BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                headers = soup.find_all("h2")

                sections = []
                for header in headers:
                    content = []
                    for sibling in header.find_next_siblings():
                        if sibling.name == "h2":
                            break
                        content.append(sibling.get_text())
                    sections.append("\n".join(content).strip())

                if len(sections) < 2:
                    raise ValueError("Markdown file must contain at least two sections for comparison.")

                results = self._evaluate_summaries(sections[0], sections[1])

                return results
