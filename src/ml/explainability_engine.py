"""
Explainability Engine for HSN Misclassification: src/ml/explainability_engine.py
Deconstructs LightGBM risk predictions using native Tree SHAP (pred_contrib=True)
and maps technical attribution drivers into human-readable, audit-ready compliance evidence.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd

from src.ml.misclassification_features import (
    FEATURE_COLUMNS,
    extract_features,
    load_metadata_tables,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT_DIR / "artifacts"

# Standard statutory HS Chapter descriptions for audit explanation mapping
CHAPTER_DESCRIPTIONS: Dict[str, str] = {
    "01": "Live Animals",
    "02": "Meat and Edible Meat Offal",
    "03": "Fish and Crustaceans",
    "04": "Dairy Produce, Eggs, Natural Honey",
    "05": "Other Animal Products",
    "06": "Live Trees and Plants",
    "07": "Edible Vegetables, Roots and Tubers",
    "08": "Edible Fruit and Nuts",
    "09": "Coffee, Tea, Mate and Spices",
    "10": "Cereals",
    "11": "Milling Industry Products",
    "12": "Oil Seeds and Oleaginous Fruits",
    "13": "Lac, Gums, Resins and Vegetable Saps",
    "14": "Vegetable Plaiting Materials",
    "15": "Animal or Vegetable Fats and Oils",
    "16": "Preparations of Meat or Fish",
    "17": "Sugars and Sugar Confectionery",
    "18": "Cocoa and Cocoa Preparations",
    "19": "Preparations of Cereals, Flour, Milk",
    "20": "Preparations of Vegetables, Fruit",
    "21": "Miscellaneous Edible Preparations",
    "22": "Beverages, Spirits and Vinegar",
    "23": "Residues and Waste from Food Industries",
    "24": "Tobacco and Tobacco Substitutes",
    "25": "Salt, Sulphur, Earths, Stone, Plaster, Cement",
    "26": "Ores, Slag and Ash",
    "27": "Mineral Fuels, Mineral Oils and Distillation Products",
    "28": "Inorganic Chemicals and Rare-Earth Metals",
    "29": "Organic Chemicals",
    "30": "Pharmaceutical Products",
    "31": "Fertilisers",
    "32": "Tanning, Dyeing Extracts, Dyes, Paints, Inks",
    "33": "Essential Oils, Perfumery, Cosmetics",
    "34": "Soap, Washing, Lubricating Preparations",
    "35": "Albuminoidal Substances, Glues, Enzymes",
    "36": "Explosives, Pyrotechnics, Matches",
    "37": "Photographic or Cinematographic Goods",
    "38": "Miscellaneous Chemical Products",
    "39": "Plastics and Articles Thereof",
    "40": "Rubber and Articles Thereof",
    "41": "Raw Hides and Skins and Leather",
    "42": "Articles of Leather, Travel Goods, Handbags",
    "43": "Furskins and Artificial Fur",
    "44": "Wood and Articles of Wood, Timber",
    "45": "Cork and Articles of Cork",
    "46": "Manufactures of Straw or Basketware",
    "47": "Pulp of Wood or Other Cellulosic Material",
    "48": "Paper and Paperboard, Articles of Paper",
    "49": "Printed Books, Newspapers, Manuscripts",
    "50": "Silk and Silk Yarn",
    "51": "Wool and Animal Hair",
    "52": "Cotton and Cotton Fabrics",
    "53": "Other Vegetable Textile Fibres, Jute",
    "54": "Man-Made Filaments",
    "55": "Man-Made Staple Fibres",
    "56": "Wadding, Felt, Nonwovens, Yarns, Twine",
    "57": "Carpets and Textile Floor Coverings",
    "58": "Special Woven Fabrics, Lace, Tapestries",
    "59": "Impregnated, Coated Textile Fabrics",
    "60": "Knitted or Crocheted Fabrics",
    "61": "Articles of Apparel, Knitted or Crocheted",
    "62": "Articles of Apparel, Not Knitted",
    "63": "Other Made-Up Textile Articles",
    "64": "Footwear, Gaiters and Parts",
    "65": "Headgear and Parts",
    "66": "Umbrellas, Walking Sticks, Whips",
    "67": "Prepared Feathers, Artificial Flowers",
    "68": "Articles of Stone, Plaster, Cement, Asbestos",
    "69": "Ceramic Products",
    "70": "Glass and Glassware",
    "71": "Natural Pearls, Precious Stones, Jewellery",
    "72": "Iron and Steel",
    "73": "Iron/Steel",
    "74": "Copper and Articles Thereof",
    "75": "Nickel and Articles Thereof",
    "76": "Aluminium and Articles Thereof",
    "78": "Lead and Articles Thereof",
    "79": "Zinc and Articles Thereof",
    "80": "Tin and Articles Thereof",
    "81": "Other Base Metals, Cermets",
    "82": "Tools, Implements, Cutlery, Base Metal Hand Tools",
    "83": "Miscellaneous Articles of Base Metal",
    "84": "Machinery",
    "85": "Electrical Machinery",
    "86": "Railway or Tramway Locomotives and Rolling-Stock",
    "87": "Vehicles",
    "88": "Aircraft, Spacecraft and Parts",
    "89": "Ships, Boats and Floating Structures",
    "90": "Precision Instruments",
    "91": "Clocks and Watches",
    "92": "Musical Instruments",
    "93": "Arms and Ammunition",
    "94": "Furniture, Bedding, Mattresses, Lamps",
    "95": "Toys, Games and Sports Requisites",
    "96": "Miscellaneous Manufactured Articles",
    "97": "Works of Art, Collectors Pieces and Antiques",
    "98": "Project Imports, Baggage, Postal Articles",
    "99": "Services",
}


def get_chapter_description(chapter_code: Union[str, int]) -> str:
    """Returns human-readable statutory chapter description."""
    chap_clean = str(chapter_code).strip().replace(".0", "").zfill(2)
    return CHAPTER_DESCRIPTIONS.get(chap_clean, f"Chapter {chap_clean}")


class HSNExplainabilityEngine:
    """
    Native Tree SHAP explainability engine for the Day 06 LightGBM Misclassification Scorer.
    Deconstructs risk predictions and generates natural language audit evidence.
    """

    def __init__(
        self,
        model: Optional[Any] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
        hsn_medians: Optional[Dict[str, float]] = None,
        chapter_medians: Optional[Dict[str, float]] = None,
        global_median_price: float = 1000.0,
    ):
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.model = model
        self.feature_names = FEATURE_COLUMNS

        # Load LightGBM model if not provided
        if self.model is None:
            model_file = self.artifacts_dir / "misclassification_lgbm.joblib"
            if model_file.exists():
                self.model = joblib.load(model_file)
            else:
                calibrator_file = self.artifacts_dir / "platt_calibrator.joblib"
                if calibrator_file.exists():
                    calibrator = joblib.load(calibrator_file)
                    self.model = getattr(calibrator, "base_estimator", None)

        # Load statutory price metadata tables
        if hsn_medians is not None:
            self.hsn_medians = hsn_medians
            self.chapter_medians = chapter_medians or {}
            self.global_median_price = float(global_median_price)
        else:
            (
                self.hsn_medians,
                self.chapter_medians,
                _,
                self.global_median_price,
            ) = load_metadata_tables(self.artifacts_dir)

    def compute_shap_contributions(
        self,
        feature_input: Union[pd.DataFrame, np.ndarray, Dict[str, Any]],
    ) -> Tuple[Dict[str, float], float]:
        """
        Extracts feature contributions using LightGBM's native prediction interface:
            shap_contributions = lgbm_model.predict(feature_vector, pred_contrib=True)

        Returns:
            Tuple of (shap_values_dict, base_value)
            where shap_values_dict maps feature names to float SHAP contributions.
        """
        if self.model is None:
            raise RuntimeError("Underlying LightGBM model not loaded for SHAP extraction.")

        # Convert input to DataFrame with FEATURE_COLUMNS
        if isinstance(feature_input, dict):
            row = [float(feature_input.get(col, 0.0)) for col in self.feature_names]
            X = pd.DataFrame([row], columns=self.feature_names).astype(np.float32)
        elif isinstance(feature_input, pd.DataFrame):
            X = feature_input[self.feature_names].astype(np.float32)
        else:
            arr = np.asarray(feature_input, dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            X = pd.DataFrame(arr, columns=self.feature_names)

        # LightGBM native Tree SHAP: returns (n_samples, n_features + 1)
        raw_contrib = self.model.predict(X, pred_contrib=True)
        if hasattr(raw_contrib, "to_numpy"):
            raw_contrib = raw_contrib.to_numpy()
        contrib_row = np.asarray(raw_contrib)[0]

        # First 6 columns are feature contributions; last column is base value / bias
        shap_values: Dict[str, float] = {}
        for idx, col in enumerate(self.feature_names):
            shap_values[col] = float(round(contrib_row[idx], 4))

        base_value = float(round(contrib_row[-1], 4))
        return shap_values, base_value

    def get_top_error_drivers(
        self,
        shap_values: Dict[str, float],
        top_k: int = 2,
    ) -> List[Tuple[str, float]]:
        """
        Identifies the top positive drivers pushing the model toward predicting an error (label = 1).
        In binary margin space, phi_j > 0 indicates an increase in misclassification log-odds.
        """
        # Sort by SHAP contribution descending
        sorted_drivers = sorted(shap_values.items(), key=lambda item: item[1], reverse=True)

        # Filter positive drivers pushing toward error
        positive_drivers = [d for d in sorted_drivers if d[1] > 0.0]

        if positive_drivers:
            return positive_drivers[:top_k]
        # Fallback to top drivers overall if none are strictly positive
        return sorted_drivers[:top_k]

    def format_driver_evidence(
        self,
        feature_name: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Converts technical SHAP driver into human-readable compliance evidence.
        Templates adhere strictly to the Day 07 audit specifications.
        """
        if feature_name == "chapter_match_flag":
            decl_chap = str(context.get("declared_chapter", "73")).strip().zfill(2)
            decl_desc = context.get("declared_chapter_desc") or get_chapter_description(decl_chap)
            pred_chap = str(context.get("predicted_chapter", "84")).strip().zfill(2)
            pred_desc = context.get("predicted_chapter_desc") or get_chapter_description(pred_chap)
            top1_score = float(context.get("top1_score", context.get("top1_similarity_score", 0.912)))
            return (
                f"Declared HSN belongs to Chapter {decl_chap} ({decl_desc}), "
                f"but semantic text matches Chapter {pred_chap} ({pred_desc}) with {top1_score * 100:.1f}% similarity."
            )

        elif feature_name == "unit_price_deviation":
            unit_price = float(context.get("unit_price", 0.0))
            median_price = float(context.get("median_price", 1000.0))
            hsn_code = str(context.get("hsn_code", "HSN"))

            # Calculate price ratio
            if median_price > 0 and unit_price > 0:
                price_ratio = max(unit_price, median_price) / min(unit_price, median_price)
            else:
                price_ratio = float(context.get("price_ratio", 1.0))

            if price_ratio >= 1.5:
                return (
                    f"Unit price of ₹{unit_price:,.2f} deviates significantly ({price_ratio:.1f}x) "
                    f"from statutory median price (₹{median_price:,.2f}) for HSN {hsn_code}."
                )
            return (
                f"Unit price of ₹{unit_price:,.2f} aligns closely ({price_ratio:.1f}x) "
                f"with statutory median price (₹{median_price:,.2f}) for HSN {hsn_code}."
            )

        elif feature_name == "margin_top1_top2":
            top1_hsn = str(context.get("top1_hsn", "Top-1"))
            top2_hsn = str(context.get("top2_hsn", "Top-2"))
            margin = float(context.get("margin", context.get("margin_top1_top2", 0.0)))
            return (
                f"Ambiguous classification: Top match {top1_hsn} barely leads alternative "
                f"{top2_hsn} by a margin of {margin:.3f}."
            )

        elif feature_name == "token_entropy":
            entropy = float(context.get("token_entropy", context.get("entropy", 0.0)))
            return (
                f"High text noise/entropy ({entropy:.2f}): Description contains unstructured serial numbers or garbled tokens."
            )

        elif feature_name == "supplier_prior_error_freq":
            sup_prior = float(context.get("supplier_prior", context.get("supplier_prior_error_freq", 0.05)))
            if sup_prior <= 0.05:
                return (
                    f"Vendor compliance profile: Supplier assigned standard neutral baseline prior ({sup_prior * 100:.1f}%) with no past violations."
                )
            return (
                f"Vendor historical risk: Supplier has a {sup_prior * 100:.1f}% "
                f"historical misclassification rate across prior filings."
            )

        elif feature_name == "top1_similarity_score":
            top1_score = float(context.get("top1_score", context.get("top1_similarity_score", 0.0)))
            return (
                f"Low semantic match confidence: Retrieval similarity score ({top1_score * 100:.1f}%) "
                f"is insufficient to guarantee correct classification."
            )

        return f"Risk factor attributed to feature '{feature_name}'."

    def explain_prediction(
        self,
        invoice_line: Dict[str, Any],
        day5_retrieval_output: Any,
        features_dict: Optional[Dict[str, Any]] = None,
        top_k_drivers: int = 2,
    ) -> Dict[str, Any]:
        """
        Coordinates Tree SHAP extraction and generates natural language evidence for an invoice line.

        Args:
            invoice_line: Original line item dictionary.
            day5_retrieval_output: Day 05 search output / candidate list.
            features_dict: Optional pre-extracted 6 tabular features.
            top_k_drivers: Number of top error drivers to deconstruct (default 2).

        Returns:
            Dict containing:
                - shap_values (Dict[str, float])
                - base_value (float)
                - top_drivers (List[Tuple[str, float]])
                - explanations (List[str])
        """
        line_copy = copy.deepcopy(invoice_line)

        # 1. Extract tabular signals if not pre-extracted
        if features_dict is None:
            feats = extract_features(
                invoice_line=line_copy,
                day5_retrieval_output=day5_retrieval_output,
                hsn_medians=self.hsn_medians,
                chapter_medians=self.chapter_medians,
                global_median_price=self.global_median_price,
            )
            pred_hsn = feats.pop("predicted_hsn", "")
        else:
            feats = dict(features_dict)
            pred_hsn = str(feats.pop("predicted_hsn", ""))

        # 2. Native Tree SHAP Extraction
        shap_values, base_value = self.compute_shap_contributions(feats)

        # 3. Identify Top-2 Positive Error Drivers
        # Vendor-history driver is excluded when no supplier GSTIN was supplied (vendor check disabled)
        driver_pool = shap_values
        if line_copy.get("vendor_check_disabled"):
            driver_pool = {k: v for k, v in shap_values.items() if k != "supplier_prior_error_freq"}
        top_drivers = self.get_top_error_drivers(driver_pool, top_k=top_k_drivers)

        # 4. Context assembly for natural language templates
        decl_hsn = str(line_copy.get("declared_hsn", "")).strip()
        decl_chap = (
            str(line_copy.get("declared_hsn_chapter", "")).strip()
            or (decl_hsn[:2] if len(decl_hsn) >= 2 else "73")
        ).zfill(2)

        # Candidate details from retrieval
        candidates = []
        if isinstance(day5_retrieval_output, list):
            candidates = day5_retrieval_output
        elif isinstance(day5_retrieval_output, dict):
            candidates = day5_retrieval_output.get("matches", day5_retrieval_output.get("candidates", []))
        elif hasattr(day5_retrieval_output, "matches"):
            candidates = getattr(day5_retrieval_output, "matches")

        top1_hsn = str(candidates[0].get("hsn_code", candidates[0].get("hsn", pred_hsn))) if candidates else pred_hsn
        top2_hsn = str(candidates[1].get("hsn_code", candidates[1].get("hsn", "alternative"))) if len(candidates) > 1 else "alternative"
        pred_chap = (top1_hsn[:2] if len(top1_hsn) >= 2 else "84").zfill(2)

        # Statutory median price lookup
        unit_price = float(line_copy.get("unit_price", line_copy.get("price", 0.0)) or 0.0)
        hsn_eval = decl_hsn if decl_hsn else top1_hsn
        median_price = (
            self.hsn_medians.get(hsn_eval)
            or self.hsn_medians.get(hsn_eval[:4])
            or self.chapter_medians.get(hsn_eval[:2])
            or self.global_median_price
        )

        context: Dict[str, Any] = {
            "declared_chapter": decl_chap,
            "declared_chapter_desc": get_chapter_description(decl_chap),
            "predicted_chapter": pred_chap,
            "predicted_chapter_desc": get_chapter_description(pred_chap),
            "top1_score": float(feats.get("top1_similarity_score", 0.90)),
            "unit_price": unit_price,
            "median_price": float(median_price),
            "hsn_code": hsn_eval,
            "top1_hsn": top1_hsn,
            "top2_hsn": top2_hsn,
            "margin": float(feats.get("margin_top1_top2", 0.0)),
            "token_entropy": float(feats.get("token_entropy", 0.0)),
            "supplier_prior": float(feats.get("supplier_prior_error_freq", 0.05)),
        }

        # 5. Format human-readable evidence strings
        explanations: List[str] = []
        for feat_name, shap_val in top_drivers:
            # Only include explanation if feature drove toward error or top drivers requested
            msg = self.format_driver_evidence(feat_name, context)
            explanations.append(msg)

        return {
            "shap_values": shap_values,
            "base_value": base_value,
            "top_drivers": top_drivers,
            "explanations": explanations,
        }
